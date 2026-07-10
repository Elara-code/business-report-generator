"""PDF 渲染器：复用 HTML 渲染 + weasyprint。"""
from __future__ import annotations

import os
import sys

try:
    from weasyprint import HTML
except Exception:  # pragma: no cover
    HTML = None

from . import html_renderer


def render(report: dict, out_path: str) -> str:
    if HTML is None:
        raise RuntimeError(
            "weasyprint 未安装或缺少系统依赖。运行：\n"
            "  brew install pango libffi  (macOS)\n"
            "  pip install weasyprint"
        )
    html = html_renderer.render(report)
    HTML(string=html, base_url=os.path.dirname(html_renderer.__file__)).write_pdf(out_path)
    return out_path
