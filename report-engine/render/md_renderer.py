"""Markdown 渲染器：纯文本版报告（不含 SVG，用 Mermaid 占位 + 表格替代）。"""
from __future__ import annotations

from datetime import datetime


def _chart_to_md(chart: dict) -> str:
    if not chart or not chart.get("type") or chart.get("type") == "null":
        return ""
    ctype = chart["type"]
    title = chart.get("title", "")
    data = chart.get("data") or {}

    md = [f"**📊 {title}**\n"]
    if ctype == "bar":
        cats = data.get("categories", [])
        vals = data.get("values", [])
        unit = data.get("unit", "")
        if cats and vals:
            md.append("| 类别 | 数值 |")
            md.append("| --- | ---: |")
            for c, v in zip(cats, vals):
                md.append(f"| {c} | {v}{unit} |")
    elif ctype == "line":
        cats = data.get("categories", [])
        series = data.get("series", [])
        if cats and series:
            header = ["时间"] + [s.get("name", "") for s in series]
            md.append("| " + " | ".join(header) + " |")
            md.append("| " + " | ".join(["---"] + ["---:"] * len(series)) + " |")
            for i, c in enumerate(cats):
                row = [c] + [str(s.get("values", [0] * len(cats))[i] if i < len(s.get("values", [])) else "") for s in series]
                md.append("| " + " | ".join(row) + " |")
    elif ctype == "radar":
        axes = data.get("axes", [])
        if "series" in data and data["series"]:
            header = ["维度"] + [s.get("name", "") for s in data["series"]]
            md.append("| " + " | ".join(header) + " |")
            md.append("| " + " | ".join(["---"] + ["---:"] * len(data["series"])) + " |")
            for i, a in enumerate(axes):
                row = [a] + [str(s.get("values", [0] * len(axes))[i] if i < len(s.get("values", [])) else "") for s in data["series"]]
                md.append("| " + " | ".join(row) + " |")
        else:
            md.append("| 维度 | 评分 |")
            md.append("| --- | ---: |")
            for a, v in zip(axes, data.get("values", [])):
                md.append(f"| {a} | {v} |")
    elif ctype == "canvas":
        cells = {
            "重要合作 (KP)": data.get("key_partners", []),
            "关键业务 (KA)": data.get("key_activities", []),
            "核心资源 (KR)": data.get("key_resources", []),
            "价值主张 (VP)": data.get("value_propositions", []),
            "客户关系 (CR)": data.get("customer_relationships", []),
            "客户细分 (CS)": data.get("customer_segments", []),
            "渠道通路 (CH)": data.get("channels", []),
            "成本结构": data.get("cost_structure", []),
            "收入来源": data.get("revenue_streams", []),
        }
        for k, v in cells.items():
            if v:
                md.append(f"**{k}**: {', '.join(v)}")
    elif ctype == "funnel":
        stages = data.get("stages", [])
        if stages:
            md.append("| 阶段 | 数量 | 累计 | 转化 |")
            md.append("| --- | ---: | ---: | ---: |")
            base = stages[0].get("value", 1)
            for i, s in enumerate(stages):
                v = s.get("value", 0)
                cum = v / base * 100 if base else 0
                conv = v / stages[i-1].get("value", 1) * 100 if i > 0 and stages[i-1].get("value") else 100
                md.append(f"| {s.get('name','')} | {v:,} | {cum:.0f}% | {conv:.0f}% |")
    elif ctype == "value_chain":
        stages = data.get("stages", [])
        for s in stages:
            items = ", ".join(s.get("items", []))
            md.append(f"- **{s.get('name','')}** (毛利 {s.get('margin','')}): {items}")
    elif ctype == "matrix":
        points = data.get("points", [])
        if points:
            md.append("| 名称 | " + data.get("x_label", "X") + " | " + data.get("y_label", "Y") + " |")
            md.append("| --- | ---: | ---: |")
            for p in points:
                md.append(f"| {p.get('name','')} | {p.get('x','')} | {p.get('y','')} |")
    return "\n".join(md)


def render(report: dict) -> str:
    meta = report.get("meta", {})
    summary = report.get("summary", "")
    sections = report.get("sections", [])
    appendix = report.get("appendix", {})

    lines = [
        f"# {meta.get('title', '商业分析报告')}",
        "",
        f"> 主题：**{meta.get('subject', '')}**  ·  类型：{meta.get('type', '')}  ·  生成于 {meta.get('generated_at', '')}",
        "",
        "## 执行摘要",
        "",
        summary,
        "",
        "---",
        "",
    ]

    for i, sec in enumerate(sections, 1):
        title = sec.get("title", f"章节 {i}")
        content = sec.get("content", "")
        chart = sec.get("chart") or {}
        lines.append(f"## {i:02d}. {title}")
        lines.append("")
        lines.append(content)
        lines.append("")
        if chart and chart.get("type") and chart.get("type") != "null":
            lines.append(_chart_to_md(chart))
            lines.append("")

    if appendix:
        lines.append("---")
        lines.append("")
        lines.append("## 附录")
        if appendix.get("data_sources"):
            lines.append("")
            lines.append("**数据来源**")
            for s in appendix["data_sources"]:
                lines.append(f"- {s}")
        if appendix.get("limitations"):
            lines.append("")
            lines.append("**局限性**")
            lines.append(appendix["limitations"])
        lines.append("")

    lines.append("---")
    lines.append(f"*由 Report Engine 生成 · {datetime.now().strftime('%Y-%m-%d')}*")

    return "\n".join(lines)
