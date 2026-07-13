"""折线图（line）。

data 格式：
{
  "categories": ["2020", "2021", "2022"],
  "series": [
    {"name": "市场规模", "values": [100, 130, 165]},
    {"name": "用户数", "values": [50, 70, 95]}
  ],
  "unit": "亿元"
}
"""
from __future__ import annotations

from ._common import PALETTE, SERIES_COLORS, esc, svg_footer, svg_header, truncate_label


def render(data: dict, title: str | None = None, width: int = 720, height: int = 320) -> str:
    cats = data.get("categories", [])
    series = data.get("series", [])
    unit = data.get("unit", "")
    if not cats or not series:
        return f'<div style="color:{PALETTE["muted"]}">（数据缺失）</div>'

    pad_l, pad_r, pad_t, pad_b = 60, 100, 50, 40
    chart_w = width - pad_l - pad_r
    chart_h = height - pad_t - pad_b
    all_vals = [v for s in series for v in s.get("values", [])]
    if not all_vals:
        return f'<div style="color:{PALETTE["muted"]}">（无数据点）</div>'
    vmax = max(all_vals) * 1.15
    vmin = min(all_vals, default=0)
    if vmin > 0:
        vmin = 0

    parts = [svg_header(width, height, title)]
    # Y 轴网格
    for i in range(5):
        y = pad_t + chart_h * i / 4
        v = vmax - (vmax - vmin) * i / 4
        parts.append(
            f'<line x1="{pad_l}" y1="{y}" x2="{pad_l + chart_w}" y2="{y}" '
            f'stroke="{PALETTE["border"]}" stroke-dasharray="2 3"/>'
        )
        parts.append(
            f'<text x="{pad_l - 8}" y="{y + 4}" text-anchor="end" font-size="11" '
            f'fill="{PALETTE["muted"]}">{v:.0f}</text>'
        )
    # X 轴标签（截断到 8 字，年份/季度等短标签不受影响）
    n = len(cats)
    for i, c in enumerate(cats):
        c_disp = truncate_label(c, max_chars=8)
        x = pad_l + chart_w * i / max(n - 1, 1)
        parts.append(
            f'<text x="{x}" y="{pad_t + chart_h + 20}" text-anchor="middle" '
            f'font-size="11" fill="{PALETTE["muted"]}">{esc(c_disp)}</text>'
        )

    # 各 series
    for si, s in enumerate(series):
        color = SERIES_COLORS[si % len(SERIES_COLORS)]
        vals = s.get("values", [])
        points = []
        for i, v in enumerate(vals):
            x = pad_l + chart_w * i / max(n - 1, 1)
            y = pad_t + chart_h * (1 - (v - vmin) / (vmax - vmin) if vmax != vmin else 0.5)
            points.append((x, y))
        # 折线
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.5" points="{poly}"/>')
        # 点
        for x, y in points:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}" stroke="white" stroke-width="2"/>')

    # 图例
    legend_x = pad_l + chart_w + 20
    for si, s in enumerate(series):
        color = SERIES_COLORS[si % len(SERIES_COLORS)]
        ly = pad_t + 20 + si * 22
        s_name = truncate_label(s.get("name", ""), max_chars=10)
        parts.append(f'<rect x="{legend_x}" y="{ly - 10}" width="14" height="14" fill="{color}" rx="3"/>')
        parts.append(
            f'<text x="{legend_x + 22}" y="{ly + 1}" font-size="12" '
            f'fill="{PALETTE["text"]}">{esc(s_name)} ({esc(unit)})</text>'
        )

    parts.append(svg_footer())
    return "\n".join(parts)
