"""HTML 渲染器：把报告 JSON 转成完整的 HTML 页面（内联 SVG + 响应式 CSS）。

安全说明：LLM 输出的 content 字段会先通过 bleach 清洗，只保留安全的标签，
避免 XSS / 注入风险。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime

import bleach
import markdown as md_lib

from .svg_templates import render_chart

HERE = os.path.dirname(os.path.abspath(__file__))

# bleach 允许的标签白名单（仅做基础 HTML 标签，禁掉所有 script / event）
ALLOWED_TAGS = [
    "p", "br", "hr", "strong", "em", "b", "i", "u", "s", "code", "pre",
    "blockquote", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "a", "table", "thead", "tbody", "tr", "th", "td", "sup",
]
ALLOWED_ATTRS = {
    "a": ["href", "title", "rel", "target", "id"],
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


# 引用匹配：[1]、[s1]、[2]
_CITE_RE = re.compile(r"\[(s?)(\d+)\]")


def _attach_citations(html: str, max_ref: int = 0) -> str:
    """把正文里的 [N] / [sN] 转成可点击的上标引用（锚点 #ref-N）。"""
    if max_ref <= 0:
        return html

    def repl(m: re.Match) -> str:
        n = int(m.group(2))
        if n <= 0 or n > max_ref:
            return m.group(0)  # 越界编号保持原样，不强行转换
        return f'<sup class="cite"><a href="#ref-{n}">[{n}]</a></sup>'

    return _CITE_RE.sub(repl, html)


def _md(text: str, max_ref: int = 0) -> str:
    """渲染 Markdown 后做 HTML 清洗，剥离 <script> 等危险标签，再挂上引用锚点。"""
    raw = md_lib.markdown(text or "", extensions=["tables", "fenced_code"])
    cleaned = _sanitize(raw)
    return _attach_citations(cleaned, max_ref=max_ref)


def _render_key_points(points, max_ref: int = 0) -> str:
    """渲染每节的要点列表（可视化优先风格：文字精炼、要点一行一条）。"""
    if not points:
        return ""
    items = []
    for p in points:
        p = str(p or "").strip()
        if not p:
            continue
        html = _attach_citations(_sanitize(md_lib.markdown(p)), max_ref=max_ref)
        items.append(f"<li>{html}</li>")
    if not items:
        return ""
    return '<ul class="key-points">' + "".join(items) + "</ul>"


def render(report: dict) -> str:
    meta = report.get("meta", {})
    summary = report.get("summary", "")
    sections = report.get("sections", [])
    appendix = report.get("appendix", {})
    evidence = report.get("evidence") or {}
    max_ref = len(evidence.get("sources") or [])   # 引用编号上限

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

        # 可视化优先：导语 → 图 → 要点
        kp_html = _render_key_points(sec.get("key_points"), max_ref)

        section_html.append(f"""
<section class="section" id="sec-{i}">
  <div class="section-num">{i:02d}</div>
  <h2 class="section-title">{_e(title)}</h2>
  <div class="section-content">{_md(content_md, max_ref)}</div>
  {f'<div class="chart-wrap">{chart_html}</div>' if chart_html else ''}
  {kp_html}
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
    # 证据与来源章节（v1：研究流水线）
    evidence_html = _render_evidence(evidence)

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
    <div class="hero-date">生成于 {_e(meta.get("generated_at", datetime.now().isoformat(timespec="seconds")))} · 数据截止 {_e((meta.get("confidence") or {}).get("data_cutoff") or "见来源说明")}</div>
  </header>

  <section class="summary">
    <div class="summary-label">执行摘要</div>
    <div class="summary-body">{_md(summary, max_ref)}</div>
  </section>

  {''.join(section_html)}
  {appendix_html}
  {evidence_html}

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


# ---------------------------------------------------------------------------
# 证据与来源章节（研究流水线 v1）
# ---------------------------------------------------------------------------

_EVIDENCE_STATUS = {
    "verified":    ("已核实", "#149c6a", "#e8f8f0"),
    "conflicted":  ("冲突",   "#dc2626", "#fef2f2"),
    "unverified":  ("待确认", "#b7791f", "#fff8e8"),
    "estimate":    ("估算",   "#b7791f", "#fff8e8"),
    "inference":   ("推断",   "#7c8798", "#f1f3f7"),
}
_TYPE_LABEL = {"official": "官方数据", "report": "行业报告", "financial": "公司财报",
               "news": "新闻报道", "media": "自媒体", "other": "其他"}


def _render_evidence(evidence: dict) -> str:
    """渲染"证据与来源"章节：事实状态表 + 带编号的来源列表。"""
    if not evidence:
        return ""
    sources = evidence.get("sources") or []
    facts = evidence.get("facts") or []
    if not sources and not facts:
        return ""

    parts = ['<section class="section evidence">',
             '<h2 class="section-title">证据与来源</h2>']

    # 事实状态（默认折叠：正文已内联标注核实状态，工作台另有"证据链"Tab 可交互查看）
    if facts:
        rows = []
        for f in facts:
            label, color, bg = _EVIDENCE_STATUS.get(f.get("status", "unverified"),
                                                    _EVIDENCE_STATUS["unverified"])
            refs = "".join(f'<sup class="cite"><a href="#ref-{n}">[{n}]</a></sup>'
                           for e in f.get("evidence", [])
                           if (n := re.sub(r"\D", "", e or "")))
            rows.append(
                f'<tr><td><span class="ev-tag" style="background:{bg};color:{color}">{label}</span></td>'
                f'<td>{_e(f.get("claim", ""))}{refs}</td>'
                f'<td>{_e(f.get("category", ""))}</td>'
                f'{f"<td>{_e(f.get('note', ''))}</td>" if f.get("note") else "<td></td>"}</tr>'
            )
        n_verified = sum(1 for f in facts if f.get("status") == "verified")
        n_conf = sum(1 for f in facts if f.get("status") == "conflicted")
        n_unv = sum(1 for f in facts if f.get("status") in ("unverified", "estimate"))
        summary = (
            '<summary class="ev-summary">事实状态总览'
            f'<span class="ev-sum-count">共 {len(facts)} 条 · '
            f'<span class="ev-sum-ok">{n_verified} 已核实</span> · '
            f'<span class="ev-sum-conf">{n_conf} 冲突</span> · '
            f'<span class="ev-sum-warn">{n_unv} 待确认</span></span></summary>'
        )
        parts.append('<details class="ev-details">' + summary +
                     '<table class="ev-table"><thead><tr>'
                     '<th>核实状态</th><th>事实</th><th>类别</th><th>说明</th>'
                     '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></details>')

    # 来源列表（带编号锚点）
    if sources:
        items = []
        for i, s in enumerate(sources, 1):
            label, color, bg = _EVIDENCE_STATUS.get(s.get("source_type", "other"), ("", "", ""))
            typ = _TYPE_LABEL.get(s.get("source_type", "other"), "其他")
            date = s.get("published_at") or s.get("accessed_at") or ""
            url = s.get("url", "")
            url_html = (f'<a href="{_e(url)}" target="_blank" rel="noopener noreferrer">'
                        f'{_e(url)}</a>') if url else ""
            items.append(
                f'<li id="ref-{i}" class="ev-src">'
                f'<span class="ref-no">[{i}]</span>'
                f'<div class="ev-src-body">'
                f'<b>{_e(s.get("title", ""))}</b>'
                f'<span class="ev-src-meta">《{typ}》 · {_e(date)}</span>'
                f'{url_html}'
                f'</div></li>'
            )
        parts.append('<h3 class="ev-h3">公开来源（可点击核验）</h3>'
                     '<ol class="ev-src-list">' + "".join(items) + '</ol>')

    parts.append('</section>')
    return "\n".join(parts)


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
