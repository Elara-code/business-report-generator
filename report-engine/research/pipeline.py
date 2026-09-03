"""研究流水线编排：检索 → 筛选 → 抽取 → 交叉验证 → 证据链。

对外提供 run_research()，接收 Searcher 与可选的 LLM 回调，
内部驱动 5 个阶段并写入 ResearchLog（供 SSE / 前端"分析过程"面板展示）。
"""
from __future__ import annotations

import time
from typing import Callable

from .models import (EvidenceChain, ResearchLog, ResearchPlan, ResearchSource,
                     ResearchStep, now_cn)
from .searcher import Searcher, _VERTICAL_BONUS, filter_dedup
from .extractor import extract_facts
from .verifier import verify_facts

Progress = Callable[[str, str], None]

_STEP_KEYS = ["parse", "search", "filter", "extract", "verify"]


def _new_log(plan: ResearchPlan) -> ResearchLog:
    return ResearchLog(steps=[
        ResearchStep(name=name, status="pending") for name in [
            "理解分析任务", "公开网络检索", "来源筛选与去重", "事实抽取", "交叉验证",
        ]
    ], started_at=now_cn())


def _set_step(log: ResearchLog, idx: int, status: str, message: str = "", detail: str = "") -> None:
    if 0 <= idx < len(log.steps):
        log.steps[idx].status = status  # type: ignore[assignment]
        if message:
            log.steps[idx].message = message
        if detail:
            log.steps[idx].detail = detail


def run_research(plan: ResearchPlan, searcher: Searcher,
                 llm: Callable | None = None,
                 on_progress: Progress | None = None,
                 max_sources: int = 12) -> EvidenceChain:
    """执行研究流水线，返回证据链。"""
    log = _new_log(plan)
    t0 = time.time()

    def emit(key: str, msg: str):
        if on_progress:
            try:
                on_progress(key, msg)
            except Exception:
                pass

    # 1) 理解分析任务（已在 planner 完成，这里直接标记）
    emit("parse", f"已解析：{plan.display}")
    _set_step(log, 0, "done", "任务解析完成", plan.display)

    # 2) 公开网络检索
    emit("search", f"开始检索 {len(plan.queries)} 组关键词…")
    _set_step(log, 1, "running", "检索中")
    raw_results = []
    for q in plan.queries:
        try:
            raw_results.extend(searcher.search(q, limit=8))
        except Exception:
            continue
    emit("search", f"检索到 {len(raw_results)} 个候选来源")
    _set_step(log, 1, "done", f"检索 {len(plan.queries)} 组关键词", f"命中 {len(raw_results)} 个候选")

    # 3) 来源筛选与去重
    emit("filter", "去重并按权威度排序…")
    _set_step(log, 2, "running", "筛选去重中")
    vertical = _VERTICAL_BONUS.get(plan.report_type, {})
    sources = filter_dedup(raw_results, max_sources=max_sources, vertical_bonus=vertical)
    emit("filter", f"筛选保留 {len(sources)} 个有效来源")
    _set_step(log, 2, "done", f"保留 {len(sources)} 个来源")

    # 4) 事实抽取
    emit("extract", "从来源中抽取关键事实…")
    _set_step(log, 3, "running", "抽取中")
    facts = extract_facts(plan, sources, llm=llm)
    emit("extract", f"抽取 {len(facts)} 条关键事实")
    _set_step(log, 3, "done", f"抽取 {len(facts)} 条事实")

    # 5) 交叉验证
    emit("verify", "进行多源交叉验证与冲突检测…")
    _set_step(log, 4, "running", "验证中")
    facts = verify_facts(facts, sources)
    n_ok = sum(1 for f in facts if f.status == "verified")
    n_conf = sum(1 for f in facts if f.status == "conflicted")
    n_unv = sum(1 for f in facts if f.status == "unverified")
    emit("verify", f"交叉验证完成：{n_ok} 已核实 · {n_conf} 冲突 · {n_unv} 待确认")
    _set_step(log, 4, "done" if n_conf == 0 else "issue",
              f"{n_ok} 已核实 · {n_conf} 冲突 · {n_unv} 待确认",
              "存在数据口径冲突" if n_conf else "多源一致")

    log.elapsed_ms = int((time.time() - t0) * 1000)
    return EvidenceChain(plan=plan, sources=sources, facts=facts, log=log)
