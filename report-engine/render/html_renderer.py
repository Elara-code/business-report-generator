"""HTML 渲染器：把报告 JSON 转成完整的 HTML 页面（内联 SVG + 响应式 CSS）。"""
from __future__ import annotations

import json
import os
from datetime import datetime

import markdown as md_lib

from .svg_templates import render_chart

HERE = os.path.dirname(os.path.abspath(__file__))


def _format_meta(report: dict) -> str:
    meta = report.get("meta", {})
    type_label = {
        "industry": "行业商业模式分析",
        "product": "产品拆解",
        "competitor": "竞品对比",
    }.get(meta.get("type", ""), "分析报告")
    return f'{meta.get("title", "商业分析报告")} · {type_label}'


def _md(text: str) -> str:
    return md_lib.markdown(text or "", extensions=["tables", "fenced_code"])


def render(report: dict) -> str:
    meta = report.get("meta", {})
    summary = report.get("summary", "")
    sections = report.get("sections", [])
    appendix = report.get("appendix", {})

    css = _read_css()

    # 各 section
    section_html = []
    for i, sec in enumerate(sections, 1):
        title = sec.get("title", f"章节 {i}")
        content_md = sec.get("content", "")
        chart = sec.get("chart") or {}
        chart_type = chart.get("type")
        chart_title = chart.get("title")
        chart_data = chart.get("data") or {}

        chart_html = ""
        if chart_type and chart_type != "null":
            try:
                chart_html = render_chart(chart_type, chart_data, chart_title)
            except Exception as e:  # noqa
                chart_html = f'<div class="chart-error">图表渲染失败: {e}</div>'

        section_html.append(f"""
<section class="section">
  <div class="section-num">{i:02d}</div>
  <h2 class="section-title">{_e(title)}</h2>
  <div class="section-content">{_md(content_md)}</div>
  {f'<div class="chart-wrap">{chart_html}</div>' if chart_html else ''}
</section>
""")

    # 附录
    appendix_html = ""
    if appendix:
        sources = appendix.get("data_sources") or []
        limitations = appendix.get("limitations") or ""
        src_html = "".join(f"<li>{_e(s)}</li>" for s in sources)
        appendix_html = f"""
<section class="section appendix">
  <h2 class="section-title">附录</h2>
  {"<h3>数据来源</h3><ul class='sources'>" + src_html + "</ul>" if src_html else ""}
  {"<h3>局限性说明</h3><p>" + _e(limitations) + "</p>" if limitations else ""}
</section>
"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_e(_format_meta(report))}</title>
<style>{css}</style>
</head>
<body>
<div class="report">
  <header class="hero">
    <div class="hero-meta">
      <span class="badge">{_e({"industry":"行业","product":"产品","competitor":"竞品"}.get(meta.get("type",""), "分析"))}</span>
      <span class="muted">·</span>
      <span class="muted">{_e(meta.get("subject", ""))}</span>
    </div>
    <h1 class="hero-title">{_e(meta.get("title", "商业分析报告"))}</h1>
    <div class="hero-date">生成于 {_e(meta.get("generated_at", datetime.now().isoformat(timespec="seconds")))}</div>
  </header>

  <section class="summary">
    <div class="summary-label">执行摘要</div>
    <div class="summary-body">{_md(summary)}</div>
  </section>

  {''.join(section_html)}
  {appendix_html}

  <footer class="report-foot">
    <span>本报告由 Report Engine 生成</span>
    <span class="muted">WorkBuddy AI · {datetime.now().strftime('%Y-%m-%d')}</span>
  </footer>
</div>
</body>
</html>"""
    return html


def _e(s: str) -> str:
    return (str(s).replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;")
                   .replace('"', "&quot;"))


def _read_css() -> str:
    css_path = os.path.join(os.path.dirname(HERE), "..", "web", "report.css")
    css_path = os.path.abspath(css_path)
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            return f.read()
    # 兜底
    return _FALLBACK_CSS


_FALLBACK_CSS = """
body{font-family:-apple-system,'PingFang SC',sans-serif;background:#f8fafc;color:#0f172a;margin:0;padding:0;}
.report{max-width:880px;margin:0 auto;padding:48px 32px;background:white;}
.hero{border-bottom:1px solid #e2e8f0;padding-bottom:24px;margin-bottom:32px;}
.hero-title{font-size:32px;margin:8px 0;}
.summary{background:#f1f5f9;padding:20px 24px;border-radius:12px;margin-bottom:32px;}
.section{margin:36px 0;}
.section-title{font-size:22px;border-left:4px solid #2563eb;padding-left:12px;margin-bottom:16px;}
.chart-wrap{margin:20px 0;padding:16px;background:#f8fafc;border-radius:12px;}
"""
