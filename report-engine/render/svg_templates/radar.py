"""雷达图（radar）。

支持单条或多条 series：
单条 data = {"axes": ["A", "B"], "values": [3, 4]}
多条 data = {"axes": [...], "series": [{"name": "A", "values": [...]}, ...]}
"""
from __future__ import annotations

import math

from ._common import PALETTE, SERIES_COLORS, esc, svg_footer, svg_header


def render(data: dict, title: str | None = None, width: int = 520, height: int = 460) -> str:
    axes = data.get("axes", [])
    if not axes:
        return f'<div style="color:{PALETTE["muted"]}">（轴缺失）</div>'

    if "series" in data and data["series"]:
        series = data["series"]
    else:
        series = [{"name": "评分", "values": data.get("values", [])}]

    cx, cy = width // 2, height // 2 + 10
    r = min(width, height) // 2 - 70
    n = len(axes)
    angle_step = 2 * math.pi / n
    max_v = 5  # 默认 0-5

    parts = [svg_header(width, height, title)]
    # 同心圆 + 网格
    for level in (1, 2, 3, 4, 5):
        rr = r * level / max_v
        pts = []
        for i in range(n):
            a = -math.pi / 2 + i * angle_step
            pts.append(f"{cx + rr * math.cos(a):.1f},{cy + rr * math.sin(a):.1f}")
        parts.append(
            f'<polygon points="{" ".join(pts)}" fill="none" '
            f'stroke="{PALETTE["border"]}" stroke-dasharray="2 3"/>'
        )
    # 轴线 + 标签
    for i, ax in enumerate(axes):
        a = -math.pi / 2 + i * angle_step
        x_end = cx + r * math.cos(a)
        y_end = cy + r * math.sin(a)
        parts.append(
            f'<line x1="{cx}" y1="{cy}" x2="{x_end:.1f}" y2="{y_end:.1f}" '
            f'stroke="{PALETTE["border"]}"/>'
        )
        # 标签在更外
        lx = cx + (r + 22) * math.cos(a)
        ly = cy + (r + 22) * math.sin(a)
        anchor = "middle"
        if math.cos(a) > 0.3:
            anchor = "start"
        elif math.cos(a) < -0.3:
            anchor = "end"
        parts.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" dominant-baseline="middle" '
            f'font-size="12" fill="{PALETTE["text"]}">{esc(ax)}</text>'
        )

    # series 多边形
    for si, s in enumerate(series):
        color = SERIES_COLORS[si % len(SERIES_COLORS)]
        vals = s.get("values", [])
        if len(vals) != n:
            vals = (vals + [0] * n)[:n]
        pts = []
        for i, v in enumerate(vals):
            a = -math.pi / 2 + i * angle_step
            rr = r * (v / max_v) if max_v else 0
            pts.append(f"{cx + rr * math.cos(a):.1f},{cy + rr * math.sin(a):.1f}")
        parts.append(
            f'<polygon points="{" ".join(pts)}" fill="{color}" fill-opacity="0.18" '
            f'stroke="{color}" stroke-width="2"/>'
        )
        for p in pts:
            x, y = p.split(",")
            parts.append(f'<circle cx="{x}" cy="{y}" r="3.5" fill="{color}" stroke="white" stroke-width="1.5"/>')

    # 图例
    if len(series) > 1:
        for si, s in enumerate(series):
            color = SERIES_COLORS[si % len(SERIES_COLORS)]
            ly = 36 + si * 22
            parts.append(f'<rect x="20" y="{ly - 10}" width="14" height="14" fill="{color}" rx="3"/>')
            parts.append(
                f'<text x="42" y="{ly + 1}" font-size="12" fill="{PALETTE["text"]}">{esc(s.get("name", ""))}</text>'
            )

    parts.append(svg_footer())
    return "\n".join(parts)
