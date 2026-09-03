"""交叉验证：给事实打上可信状态，并检测不同来源的数值冲突。

规则（离线可用，确定性）：
1. 多源判定：≥2 个独立来源 → verified；恰 1 个来源 → unverified；无来源 → estimate；
2. 数值冲突：同一类别下不同事实出现互不相同的数字 → 标记 conflicted（报告同时展示）；
3. 置信度计算：由核实比例 + 冲突情况得出（替代 LLM 自评）。
"""
from __future__ import annotations

import re
from collections import defaultdict

from .models import Fact, ResearchSource


def verify_facts(facts: list[Fact], sources: list[ResearchSource]) -> list[Fact]:
    """就地更新每个 Fact 的 status，返回原列表。

    核实模型（专业精准）：
    - 先做「数值级对齐合并」：同一类别聚合指标、数值相交的不同表述 → 合并来源证据，
      弥补 LLM 抽取时表述差异导致的多源事实合并不上（根因修复）；
    - ≥2 个独立来源 → verified（多源交叉）；
    - 恰 1 个来源且权威度 ≥ 0.75（官方数据 / 公司财报 / 权威行业报告）→ verified（高权威单源）；
    - 恰 1 个低权威来源 → unverified；无来源 → estimate。
    """
    src_ids = {getattr(s, "id", None) or f"s{i}" for i, s in enumerate(sources, 1)}
    quality = {getattr(s, "id", None) or f"s{i}": getattr(s, "quality_score", 0.5)
               for i, s in enumerate(sources, 1)}

    # 0) 数值级对齐合并（确定性兜底，弥补抽取阶段跨来源表述差异）
    _merge_same_numeric(facts)

    # 1) 多源 + 权威度加权判定
    for f in facts:
        ev = [e for e in f.evidence if e in src_ids]
        f.evidence = ev
        n = len(set(ev))
        if n >= 2:
            f.status = "verified"
        elif n == 1:
            q = quality.get(ev[0], 0.5)
            if q >= 0.75:
                f.status = "verified"  # 高权威单源（官方/财报/权威报告）
                if "来源" not in (f.note or ""):
                    f.note = (f.note + "；单一权威来源").strip("；")
            else:
                f.status = "unverified"
        else:
            f.status = "estimate"
            f.note = (f.note + "；无直接来源，属估算").strip("；")

    # 2) 数值冲突检测（同类别出现不同数字）
    _mark_conflicts(facts)
    return facts


_MERGE_CATEGORIES = {"市场规模", "营收", "收入", "估值", "销售额", "融资", "GMV", "增速", "份额", "规模"}


def _is_numeric_category(category: str) -> bool:
    """该类别是否属于"数值型聚合指标"（同类别同数值可判定为同一事实）。"""
    return any(c in (category or "") for c in _MERGE_CATEGORIES)


def _merge_same_numeric(facts: list[Fact]) -> None:
    """数值级对齐合并：同类别、数值型聚合指标、绝对数值集合相交 → 合并来源证据。

    背景：不同来源对同一事实的表述几乎必然不同（"市场规模达 7000 亿美元" vs
    "现制咖啡市场约 7000 亿"），LLM 抽取时难以保证按 claim 合并；这里在验证阶段
    用「数值型类别 + 数值相交」做确定性对齐，使同一事实获得多来源支持 → 判为已核实。
    仅合并 evidence，不改动 claim / note，避免信息丢失。
    """
    by_cat: dict[str, list[Fact]] = defaultdict(list)
    for f in facts:
        if f.category:
            by_cat[f.category].append(f)

    for group in by_cat.values():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if not (_is_numeric_category(a.category) and _is_numeric_category(b.category)):
                    continue
                if not (_is_aggregate_metric(a.claim) or _is_aggregate_metric(b.claim)):
                    continue  # claim 上无聚合指标线索则保守不合并（防门店数/员工数误并）
                if a.claim == b.claim:
                    continue  # 字符串已相同，无需数值对齐
                na = set(round(x) for x in _big_numbers(a.claim))
                nb = set(round(x) for x in _big_numbers(b.claim))
                if na and nb and not na.isdisjoint(nb):
                    # 数值相交 → 视为同一事实的不同表述，互相补全来源
                    for src in list(a.evidence):
                        if src not in b.evidence:
                            b.evidence.append(src)
                    for src in list(b.evidence):
                        if src not in a.evidence:
                            a.evidence.append(src)


def _big_numbers(claim: str) -> list[float]:
    """抽取"绝对规模"数字（非百分比、非年份、数值 ≥ 100），用于冲突检测。

    目的：市场规模/营收/门店数等绝对量出现两个口径才判"冲突"；
    百分比（CAGR、市占率）的细微差异、以及"2024 年"这类年份不视为数字。
    """
    nums = []
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*([%％万亿年]?)", claim or ""):
        v = float(m.group(1))
        unit = m.group(2)
        if unit in ("%", "％", "年"):
            continue
        if unit == "" and 1900 <= v <= 2100:
            continue  # 裸年份（如 "2024"）
        if v >= 100:
            nums.append(v)
    return nums


_METRIC_ANCHORS = ("市场规模", "营收", "收入", "估值", "销售额", "融资", "GMV")


def _is_aggregate_metric(claim: str) -> bool:
    """判断论断是否属于"聚合指标"（市场规模/营收/估值等）。

    只有同属聚合指标的不同数字才视为"口径冲突"；
    不同公司的门店数 / 不同公司的营收并不互相冲突，避免误报。
    """
    return any(a in claim for a in _METRIC_ANCHORS)


def _mark_conflicts(facts: list[Fact]) -> None:
    by_cat: dict[str, list[Fact]] = defaultdict(list)
    for f in facts:
        if f.category:
            by_cat[f.category].append(f)

    for cat, group in by_cat.items():
        if len(group) < 2:
            continue
        # 给每组内事实做两两比较：同为"聚合指标"且绝对规模数字不相交 → 冲突
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if a.status == "conflicted" and b.status == "conflicted":
                    continue
                if not (_is_aggregate_metric(a.claim) and _is_aggregate_metric(b.claim)):
                    continue
                na = set(round(x) for x in _big_numbers(a.claim))
                nb = set(round(x) for x in _big_numbers(b.claim))
                if na and nb and na.isdisjoint(nb):
                    a.status = "conflicted"
                    b.status = "conflicted"
                    a.note = f"与「{b.claim[:30]}…」口径不一致，请同时展示两种口径"
                    b.note = f"与「{a.claim[:30]}…」口径不一致，请同时展示两种口径"


# ---------------------------------------------------------------------------
# 置信度（可计算，替代 LLM 自评）
# ---------------------------------------------------------------------------

def compute_confidence(facts: list[Fact]) -> dict:
    """由事实核实状态计算报告级置信度。"""
    total = max(len(facts), 1)
    verified = sum(1 for f in facts if f.status == "verified")
    conflicted = sum(1 for f in facts if f.status == "conflicted")
    unverified = sum(1 for f in facts if f.status == "unverified")
    estimate = sum(1 for f in facts if f.status == "estimate")

    ratio = verified / total
    score = round(0.25 + 0.70 * ratio, 2)      # 0.25 ~ 0.95
    if conflicted:
        score = min(score, 0.60)                # 存在冲突时封顶
    score = max(score, 0.10)

    if score >= 0.80:
        level = "high"
    elif score >= 0.55:
        level = "medium"
    elif score >= 0.30:
        level = "low"
    else:
        level = "unknown"

    factors = [f"已核实 {verified} 条", f"待确认 {unverified} 条"]
    if conflicted:
        factors.append(f"冲突 {conflicted} 条")
    if estimate:
        factors.append(f"估算 {estimate} 条")
    if conflicted:
        recommended = "存在数据口径冲突，仅供快速浏览，关键数字请以原始来源为准"
    elif level == "high":
        recommended = "关键事实多源交叉核实，可作一般决策参考"
    elif level == "medium":
        recommended = "部分事实待确认，建议对关键结论二次核实"
    else:
        recommended = "事实覆盖不足，仅作方向性参考"

    return {
        "level": level,
        "score": score,
        "reasoning": f"基于 {total} 条事实：{verified} 条多源核实、{unverified} 条单源、"
                     f"{estimate} 条估算" + (f"、{conflicted} 条冲突" if conflicted else ""),
        "factors": factors,
        "data_cutoff": "",
        "recommended_use": recommended,
    }
