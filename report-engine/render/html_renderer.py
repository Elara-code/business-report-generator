"""HTML 渲染器：把报告 JSON 转成完整的 HTML 页面（内联 SVG + 响应式 CSS）。

安全说明：LLM 输出的 content 字段会先通过 bleach 清洗，只保留安全的标签，
避免 XSS / 注入风险。
"""
from __future__ import annotations

import json
import os
from datetime import datetime

import bleach
import markdown as md_lib

from .svg_templates import render_chart

HERE = os.path.dirname(os.path.abspath(__file__))

# bleach 允许的标签白名单（仅做基础 HTML 标签，禁掉所有 script / event）
ALLOWED_TAGS = [
    "p", "br", "hr", "strong", "em", "b", "i", "u", "s", "code", "pre",
    "blockquote", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "a", "table", "thead", "tbody", "tr", "th", "td",
]
ALLOWED_ATTRS = {
    "a": ["href", "title", "rel", "target"],
    "th": ["align"],
    "td": ["align"],
}
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def _sanitize(html: str) -> str:
    """清洗 markdown 渲染出的 HTML，去除危险标签和属性。"""
    cleaned = bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,  # 危险标签直接删掉，而不是转义
    )
    # 给所有链接加 rel="noopener noreferrer"
    from bleach.css_sanitizer import CSSSanitizer
    # 强制外链安全属性
    return cleaned


def _format_meta(report: dict) -> str:
    meta = report.get("meta", {})
    type_label = {
        "industry": "行业商业模式分析",
        "product": "产品拆解",
        "competitor": "竞品对比",
    }.get(meta.get("type", ""), "分析报告")
    return f'{meta.get("title", "商业分析报告")} · {type_label}'


def _md(text: str) -> str:
    """渲染 Markdown 后做 HTML 清洗，剥离 <script> 等危险标签。"""
    raw = md_lib.markdown(text or "", extensions=["tables", "fenced_code"])
    return _sanitize(raw)


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

    # 置信度徽章（v0.3）
    confidence_html = _render_confidence_badge(meta.get("confidence"))

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
      {confidence_html}
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


# ---------------------------------------------------------------------------
# 置信度徽章（v0.3 新增）
# ---------------------------------------------------------------------------

CONFIDENCE_STYLES = {
    "high":    {"color": "#10b981", "label": "高置信", "icon": "✓"},
    "medium":  {"color": "#f59e0b", "label": "中置信", "icon": "!"},
    "low":     {"color": "#ef4444", "label": "低置信", "icon": "⚠"},
    "unknown": {"color": "#94a3b8", "label": "未评估", "icon": "?"},
}


def _render_confidence_badge(conf: dict | None) -> str:
    """渲染置信度徽章 + 悬浮提示。"""
    if not conf:
        return ""
    level = conf.get("level", "unknown")
    style = CONFIDENCE_STYLES.get(level, CONFIDENCE_STYLES["unknown"])
    score = conf.get("score", 0.5)
    reasoning = conf.get("reasoning", "")
    recommended = conf.get("recommended_use", "")

    tooltip_parts = [f"<b>置信度评分：{score:.2f}/1.0</b>"]
    if reasoning:
        tooltip_parts.append(f"<div style='margin-top:6px'>{_e(reasoning)}</div>")
    if recommended:
        tooltip_parts.append(f"<div style='margin-top:6px;font-style:italic'>建议用途：{_e(recommended)}</div>")
    tooltip = "".join(tooltip_parts).replace('"', '&quot;')

    return f'''
<span class="confidence-badge" style="background:{style["color"]}1a;color:{style["color"]};border:1px solid {style["color"]}66;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;cursor:help" title="{tooltip}">
  {style["icon"]} {style["label"]}
</span>'''


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
