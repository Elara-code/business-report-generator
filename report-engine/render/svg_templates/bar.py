"""横向条形图（bar）。

data 格式：
{
  "categories": ["A", "B", "C"],
  "values": [25, 18, 12],
  "unit": "%"
}
"""
from __future__ import annotations

from ._common import PALETTE, SERIES_COLORS, esc, svg_footer, svg_header, text_width


def render(data: dict, title: str | None = None, width: int = 720, row_h: int = 36) -> str:
    cats = data.get("categories", [])
    vals = data.get("values", [])
    unit = data.get("unit", "")
    if not cats or not vals or len(cats) != len(vals):
        return f'<div style="color:{PALETTE["muted"]}">（数据缺失，跳过图表）</div>'

    label_w = max(text_width(c, 13) for c in cats) + 16
    value_w = max(text_width(f"{v}{unit}", 13) for v in vals) + 12
    bar_area_w = width - label_w - value_w - 40
    max_v = max(vals) if vals else 1
    n = len(cats)
    height = max(80, 50 + n * row_h)

    parts = [svg_header(width, height, title)]
    for i, (c, v) in enumerate(zip(cats, vals)):
        y = 50 + i * row_h
        bar_w = (v / max_v) * bar_area_w if max_v else 0
        color = SERIES_COLORS[i % len(SERIES_COLORS)]
        # 标签
        parts.append(
            f'<text x="{label_w}" y="{y + row_h/2 + 4}" text-anchor="end" '
            f'font-size="13" fill="{PALETTE["text"]}">{esc(c)}</text>'
        )
        # 条
        parts.append(
            f'<rect x="{label_w + 8}" y="{y + 6}" width="{bar_w}" height="{row_h - 12}" '
            f'rx="4" fill="{color}"/>'
        )
        # 数值
        parts.append(
            f'<text x="{label_w + 8 + bar_w + 6}" y="{y + row_h/2 + 4}" '
            f'font-size="12" fill="{PALETTE["muted"]}">{esc(v)}{esc(unit)}</text>'
        )
    parts.append(svg_footer())
    return "\n".join(parts)
