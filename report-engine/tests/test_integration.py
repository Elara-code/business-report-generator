"""集成测试：取消机制 + 渲染锚点（HTTP 服务层之外的端到端链路验证）。"""

import os
import threading

import pytest

import generate
from research import build_plan


def test_cancel_preset_aborts():
    """cancel_event 预置 → 第一次进度回调即抛 GenerationCancelled。"""
    ev = threading.Event()
    ev.set()
    with pytest.raises(generate.GenerationCancelled):
        generate.do_generate(report_type="industry", subject="测试", ai="mock",
                             preset=None, formats=["html"],
                             out_root="/tmp/brg_it_cancel1", from_json=None,
                             cancel_event=ev)


def test_cancel_mid_search_aborts():
    """用户在 search 阶段点取消 → 流水线中断并抛 GenerationCancelled。"""
    ev = threading.Event()

    def on_progress(phase, msg):
        if phase == "search":
            ev.set()

    with pytest.raises(generate.GenerationCancelled):
        generate.do_generate(report_type="industry", subject="咖啡", ai="mock",
                             preset="coffee", formats=["html"],
                             out_root="/tmp/brg_it_cancel2", from_json=None,
                             on_progress=on_progress, cancel_event=ev)


def test_html_renders_section_anchors():
    """生成的 HTML 每节应带 id=sec-{i} 锚点（单节重生成跳转依赖）。"""
    report, outputs, _ = generate.do_generate(
        report_type="industry", subject="中国现制咖啡", ai="mock", preset="coffee",
        formats=["html"], out_root="/tmp/brg_it_anchor", from_json=None)
    with open(outputs["html"], "r", encoding="utf-8") as f:
        html = f.read()
    n = len(report.sections)
    assert n >= 1
    for i in range(1, min(n, 3) + 1):
        assert f'id="sec-{i}"' in html


def test_plan_queries_nonempty():
    """三种报告类型的检索计划都必须非空且可用。"""
    for rt in ("industry", "product", "competitor"):
        plan = build_plan(rt, "Notion vs Obsidian" if rt == "competitor" else "测试")
        assert plan.queries
        assert all(q.strip() for q in plan.queries)
