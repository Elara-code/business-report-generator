"""事实抽取：从来源中抽取出可追溯的关键事实。

- 离线/演示模式：来源自带 seed_facts（演示语料直供），直接转成 Fact；
- 真实模式：调用 LLM 逐条抽取，每条事实绑定来源编号；
- 兜底：从摘要文本抽取"待确认"事实，保证流水线不中断。
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from .models import EvidenceChain, Fact, ResearchPlan, ResearchSource

# 各报告类型应覆盖的事实类别
CATEGORIES = {
    "industry": ["市场规模", "增速", "产业链", "竞争格局", "头部玩家", "趋势", "风险"],
    "product": ["定位", "目标用户", "核心功能", "商业模式", "定价", "增长"],
    "competitor": ["功能对比", "定价对比", "用户对比", "优势", "劣势"],
}

# LLM 回调签名：complete(system, user, json_mode) -> str
LLMCallable = Callable[..., str]


def _guess_category(claim: str, report_type: str) -> str:
    for cat in CATEGORIES.get(report_type, CATEGORIES["industry"]):
        if cat in claim:
            return cat
    return "其他"


def _numeric_snapshot(claim: str) -> list[str]:
    """抽取事实中的数字（含单位），用于冲突检测。"""
    return re.findall(r"\d+(?:\.\d+)?\s*[%％万亿千元美元]?", claim or "")


# ---------------------------------------------------------------------------
# LLM 抽取
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = """你是严谨的行业研究助手。你的任务是从给定的公开来源摘要中抽取关键事实。
规则：
1. 只抽取来源内容中明确出现的事实，绝不编造；
2. 每条事实必须标注它来自哪些来源编号（数字，对应 sources 列表序号）；
3. 事实类别从给定类别中选择；
4. 只输出 JSON 数组，不要任何其他文字。
输出格式：[{"claim": "事实描述（含具体数字）", "category": "类别", "source_ids": [1,2], "note": "补充说明"}]
"""


def _llm_extract(llm: LLMCallable, plan: ResearchPlan, sources: list[ResearchSource]) -> list[dict]:
    cats = "、".join(CATEGORIES.get(plan.report_type, CATEGORIES["industry"]))
    src_lines = []
    for i, s in enumerate(sources, 1):
        snippet = (s.snippet or "")[:300].replace("\n", " ")
        src_lines.append(f"[{i}] {s.title} | {s.url} | {s.published_at} | {snippet}")
    user = (
        f"报告主题：{plan.subject}（{plan.report_type}）\n"
        f"可用的事实类别：{cats}\n"
        f"来源列表：\n" + "\n".join(src_lines) +
        "\n\n请抽取 8-15 条关键事实，输出 JSON 数组。"
    )
    raw = llm(_EXTRACT_SYSTEM, user, json_mode=True)
    # 解析
    text = raw.strip()
    m = re.search(r"\[[\s\S]*\]", text)
    data = json.loads(m.group(0)) if m else json.loads(text)
    return data if isinstance(data, list) else []


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def _add_or_merge(facts: list[Fact], claim: str, category: str,
                  src_id: str, status: str, note: str) -> None:
    """同一 claim 出现在多个来源时合并证据（这是多源"已核实"的前提）。"""
    for f in facts:
        if f.claim == claim:
            if src_id not in f.evidence:
                f.evidence.append(src_id)
            return
    facts.append(Fact(
        id=f"f{len(facts) + 1}",
        claim=claim,
        category=category,
        evidence=[src_id],
        status=status,  # type: ignore[arg-type]
        note=note,
    ))


def extract_facts(plan: ResearchPlan, sources: list[ResearchSource],
                  llm: LLMCallable | None = None) -> list[Fact]:
    """返回 Facts。id 形如 f1, f2 ..."""
    facts: list[Fact] = []

    # 1) 演示语料直供事实（离线模式优先；重复 claim 跨来源自动合并证据）
    for idx, s in enumerate(sources, 1):
        sid = getattr(s, "id", None) or f"s{idx}"          # ResearchSource 有 id，SearchResult 用序号兜底
        seed_facts = getattr(s, "seed_facts", None) or getattr(s, "facts", []) or []
        for sf in seed_facts:
            if isinstance(sf, Fact):
                claim, category, note = sf.claim, sf.category, sf.note
            else:
                claim = str(sf.get("claim", "")).strip()  # type: ignore[union-attr]
                category = str(sf.get("category", "") or "")
                note = str(sf.get("note", "") or "")
            if not claim:
                continue
            _add_or_merge(facts, claim,
                          category or _guess_category(claim, plan.report_type),
                          sid, "unverified", note or "演示语料直供，待交叉验证")

    # 2) LLM 抽取（真实模式，且语料直供不足时）
    if llm is not None and len(facts) < 4:
        try:
            for item in _llm_extract(llm, plan, sources):
                claim = str(item.get("claim", "")).strip()
                if not claim:
                    continue
                for n in item.get("source_ids", []):
                    if isinstance(n, int):
                        _add_or_merge(facts, claim,
                                      str(item.get("category", "") or _guess_category(claim, plan.report_type)),
                                      f"s{n}", "unverified",
                                      str(item.get("note", "") or ""))
        except Exception:
            pass  # 抽取失败不阻塞，进入兜底

    # 3) 兜底：从来源摘要生成"待确认"事实（保证流水线不中断）
    if not facts:
        for idx, s in enumerate(sources[:6], 1):
            claim = (getattr(s, "snippet", None) or "").strip()[:80]
            if not claim:
                continue
            sid = getattr(s, "id", None) or f"s{idx}"
            _add_or_merge(facts, claim + "（来源摘要摘录）", "其他", sid,
                          "unverified", "来源摘要兜底，待人工确认")

    return facts
