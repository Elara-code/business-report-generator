"""意图解析 + 检索词规划（规则驱动，轻量、可离线）。

把用户的一句话输入解析成结构化研究任务（市场/时间/读者默认值），
并为报告类型生成多组检索词，交给 Searcher 并行检索。
"""
from __future__ import annotations

import re

from .models import ResearchPlan, now_cn

TYPE_LABEL = {
    "industry": "行业分析",
    "product": "产品拆解",
    "competitor": "竞品对比",
}

# 竞品对比的分隔符
_COMPARE_SEPS = re.compile(r"\s*(?:vs\.?|VS\.?|对比|比较|and|&|、|与)\s*")


def _split_competitors(subject: str) -> list[str]:
    """从 'A vs B vs C' 中拆出产品名单。"""
    parts = [p.strip() for p in _COMPARE_SEPS.split(subject) if p.strip()]
    # 去重保序
    seen: list[str] = []
    for p in parts:
        if p and p not in seen:
            seen.append(p)
    return seen or [subject]


def build_plan(report_type: str, subject: str, *,
               market: str = "", time_range: str = "", audience: str = "") -> ResearchPlan:
    """生成研究计划。用户未传的参数一律使用默认值。"""
    subject = (subject or "").strip() or "未命名"
    market = (market or "").strip() or "全国"
    time_range = (time_range or "").strip() or "近1年"
    audience = (audience or "").strip() or "普通读者"

    queries = _build_queries(report_type, subject, market)
    display = (f"{TYPE_LABEL.get(report_type, report_type)} · 市场：{market}"
               f" · 时间范围：{time_range} · 读者：{audience}")
    return ResearchPlan(
        report_type=report_type,
        subject=subject,
        market=market,
        time_range=time_range,
        audience=audience,
        queries=queries,
        display=display,
    )


def _build_queries(report_type: str, subject: str, market: str) -> list[str]:
    """为报告类型生成多路检索词（垂直化：注入权威词/年份/类型词，让来源更聚焦）。"""
    area = "全国" if market in ("全国", "中国", "中国大陆", "") else market
    year = str(int(now_cn()[:4]))  # 当前年份，提升时效性
    if report_type == "industry":
        return [
            f"{subject} 行业 市场规模 {area} {year}",
            f"{subject} 行业报告 白皮书 趋势",
            f"{subject} 产业链 价值链 上下游",
            f"{subject} 竞争格局 头部企业 市场份额",
            f"{subject} 政策 风险 机会 展望",
        ]
    if report_type == "product":
        return [
            f"{subject} 产品 介绍 核心功能 评测",
            f"{subject} 定价 商业模式 盈利",
            f"{subject} 用户 评价 口碑 优缺点",
            f"{subject} 增长 融资 最新动态 {year}",
        ]
    # competitor
    names = _split_competitors(subject)
    if len(names) >= 2:
        a, b = names[0], names[1]
        return [
            f"{a} vs {b} 对比 评测 差异",
            f"{a} {b} 区别 功能 定价 对比",
            f"{a} {b} 优缺点 用户评价 选哪个",
        ]
    return [
        f"{subject} 竞品 对比 评测",
        f"{subject} 竞品 分析 差异化",
    ]


def now_cn_str() -> str:
    return now_cn()
