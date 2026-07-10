"""SVG 模板统一入口：按 chart_type 路由。"""
from __future__ import annotations

from . import bar, canvas, funnel, line, matrix, radar, value_chain

DISPATCH = {
    "bar": bar.render,
    "line": line.render,
    "radar": radar.render,
    "canvas": canvas.render,
    "funnel": funnel.render,
    "value_chain": value_chain.render,
    "matrix": matrix.render,
}


def render_chart(chart_type: str | None, data: dict, title: str | None = None) -> str:
    if not chart_type or chart_type == "null":
        return ""
    fn = DISPATCH.get(chart_type)
    if not fn:
        return f'<div style="color:#64748b">（未知图表类型: {chart_type}）</div>'
    return fn(data, title=title)
