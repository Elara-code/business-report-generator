"""漏斗图（funnel）。

data 格式：
{
  "stages": [
    {"name": "访问", "value": 10000},
    {"name": "注册", "value": 4200},
    {"name": "付费", "value": 800}
  ]
}
"""
from __future__ import annotations

from ._common import PALETTE, SERIES_COLORS, esc, svg_footer, svg_header


def render(data: dict, title: str | None = None, width: int = 720, height: int = 360) -> str:
    stages = data.get("stages", [])
    if not stages:
        return f'<div style="color:{PALETTE["muted"]}">（数据缺失）</div>'

    max_v = max(s.get("value", 0) for s in stages) or 1
    n = len(stages)
    pad_t, pad_b, pad_l, pad_r = 50, 30, 100, 200
    chart_h = height - pad_t - pad_b
    stage_h = chart_h / n

    parts = [svg_header(width, height, title)]
    for i, s in enumerate(stages):
        v = s.get("value", 0)
        name = s.get("name", "")
        # 标签在左
        parts.append(
            f'<text x="{pad_l - 12}" y="{pad_t + stage_h * (i + 0.5) + 4}" text-anchor="end" '
            f'font-size="13" font-weight="500" fill="{PALETTE["text"]}">{esc(name)}</text>'
        )
        # 漏斗梯形
        next_v = stages[i + 1]["value"] if i + 1 < n else v * 0.85
        w_top = (v / max_v) * (width - pad_l - pad_r)
        w_bot = (next_v / max_v) * (width - pad_l - pad_r)
        y_top = pad_t + stage_h * i + 8
        y_bot = pad_t + stage_h * (i + 1) - 8
        x_center = pad_l + (width - pad_l - pad_r) / 2
        color = SERIES_COLORS[i % len(SERIES_COLORS)]
        pts = (
            f"{x_center - w_top/2:.1f},{y_top} "
            f"{x_center + w_top/2:.1f},{y_top} "
            f"{x_center + w_bot/2:.1f},{y_bot} "
            f"{x_center - w_bot/2:.1f},{y_bot}"
        )
        parts.append(f'<polygon points="{pts}" fill="{color}" fill-opacity="0.85"/>')
        # 数值 + 转化率
        ratio = v / stages[0]["value"] * 100 if i > 0 and stages[0]["value"] else 100
        conv = v / stages[i-1]["value"] * 100 if i > 0 and stages[i-1]["value"] else 100
        label_x = x_center + max(w_top, w_bot) / 2 + 16
        parts.append(
            f'<text x="{label_x}" y="{pad_t + stage_h * (i + 0.5) - 2}" font-size="13" '
            f'font-weight="600" fill="{PALETTE["text"]}">{esc(v):,}</text>'
        )
        parts.append(
            f'<text x="{label_x}" y="{pad_t + stage_h * (i + 0.5) + 14}" font-size="11" '
            f'fill="{PALETTE["muted"]}">累计 {ratio:.0f}% · 转化 {conv:.0f}%</text>'
        )
    parts.append(svg_footer())
    return "\n".join(parts)
