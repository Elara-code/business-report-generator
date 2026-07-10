"""2x2 象限图（matrix）。

data 格式：
{
  "x_label": "易用性",
  "y_label": "功能深度",
  "points": [
    {"name": "Notion", "x": 4.5, "y": 4.8},
    ...
  ]
}
"""
from __future__ import annotations

from ._common import PALETTE, SERIES_COLORS, esc, svg_footer, svg_header


def render(data: dict, title: str | None = None, width: int = 560, height: int = 480) -> str:
    x_label = data.get("x_label", "X")
    y_label = data.get("y_label", "Y")
    points = data.get("points", [])
    if not points:
        return f'<div style="color:{PALETTE["muted"]}">（无点位）</div>'

    pad_l, pad_r, pad_t, pad_b = 80, 60, 60, 70
    chart_w = width - pad_l - pad_r
    chart_h = height - pad_t - pad_b
    x_min, x_max = 0, 5
    y_min, y_max = 0, 5

    def to_xy(x, y):
        px = pad_l + (x - x_min) / (x_max - x_min) * chart_w
        py = pad_t + (1 - (y - y_min) / (y_max - y_min)) * chart_h
        return px, py

    parts = [svg_header(width, height, title)]
    # 四象限背景
    cx, cy = to_xy((x_min + x_max) / 2, (y_min + y_max) / 2)
    parts.append(f'<rect x="{pad_l}" y="{pad_t}" width="{cx - pad_l}" height="{cy - pad_t}" fill="{PALETTE["primary_lighter"]}" fill-opacity="0.3"/>')
    parts.append(f'<rect x="{cx}" y="{pad_t}" width="{pad_l + chart_w - cx}" height="{cy - pad_t}" fill="{PALETTE["accent_light"]}" fill-opacity="0.3"/>')
    parts.append(f'<rect x="{pad_l}" y="{cy}" width="{cx - pad_l}" height="{pad_t + chart_h - cy}" fill="{PALETTE["bg"]}"/>')
    parts.append(f'<rect x="{cx}" y="{cy}" width="{pad_l + chart_w - cx}" height="{pad_t + chart_h - cy}" fill="{PALETTE["bg"]}"/>')

    # 轴
    parts.append(
        f'<line x1="{pad_l}" y1="{pad_t + chart_h}" x2="{pad_l + chart_w}" y2="{pad_t + chart_h}" '
        f'stroke="{PALETTE["text"]}" stroke-width="1.5"/>'
    )
    parts.append(
        f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t + chart_h}" '
        f'stroke="{PALETTE["text"]}" stroke-width="1.5"/>'
    )
    # 中线
    parts.append(
        f'<line x1="{cx}" y1="{pad_t}" x2="{cx}" y2="{pad_t + chart_h}" '
        f'stroke="{PALETTE["border"]}" stroke-dasharray="3 3"/>'
    )
    parts.append(
        f'<line x1="{pad_l}" y1="{cy}" x2="{pad_l + chart_w}" y2="{cy}" '
        f'stroke="{PALETTE["border"]}" stroke-dasharray="3 3"/>'
    )
    # 轴标签
    parts.append(
        f'<text x="{pad_l + chart_w/2}" y="{pad_t + chart_h + 35}" text-anchor="middle" '
        f'font-size="13" font-weight="600" fill="{PALETTE["text"]}">{esc(x_label)} →</text>'
    )
    parts.append(
        f'<text x="{pad_l - 35}" y="{pad_t + chart_h/2}" text-anchor="middle" '
        f'font-size="13" font-weight="600" fill="{PALETTE["text"]}" '
        f'transform="rotate(-90, {pad_l - 35}, {pad_t + chart_h/2})">↑ {esc(y_label)}</text>'
    )
    # 刻度
    for i in range(1, 5):
        gx = pad_l + chart_w * i / 5
        parts.append(f'<line x1="{gx}" y1="{pad_t + chart_h}" x2="{gx}" y2="{pad_t + chart_h + 4}" stroke="{PALETTE["text"]}"/>')
        parts.append(f'<text x="{gx}" y="{pad_t + chart_h + 16}" text-anchor="middle" font-size="10" fill="{PALETTE["muted"]}">{i}</text>')
    for i in range(1, 5):
        gy = pad_t + chart_h * (1 - i / 5)
        parts.append(f'<line x1="{pad_l - 4}" y1="{gy}" x2="{pad_l}" y2="{gy}" stroke="{PALETTE["text"]}"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{gy + 3}" text-anchor="end" font-size="10" fill="{PALETTE["muted"]}">{i}</text>')

    # 点
    for i, p in enumerate(points):
        px, py = to_xy(p["x"], p["y"])
        color = SERIES_COLORS[i % len(SERIES_COLORS)]
        parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="11" fill="{color}" fill-opacity="0.25"/>')
        parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="6" fill="{color}"/>')
        # 标签：交错放右上 / 右下避免重叠
        offset_y = -14 if i % 2 == 0 else 18
        parts.append(
            f'<text x="{px + 12}" y="{py + offset_y}" font-size="12" font-weight="600" '
            f'fill="{PALETTE["text"]}">{esc(p.get("name", ""))}</text>'
        )

    parts.append(svg_footer())
    return "\n".join(parts)
