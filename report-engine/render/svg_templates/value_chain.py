"""价值链图（value_chain）：横向节点 + 流向箭头。

data 格式：
{
  "stages": [
    {"name": "上游", "items": ["原材料", "设备"], "margin": "高"},
    {"name": "中游", "items": ["生产", "加工"], "margin": "中"},
    {"name": "下游", "items": ["分销", "零售"], "margin": "低"}
  ]
}
"""
from __future__ import annotations

from ._common import PALETTE, esc, svg_footer, svg_header, text_width


MARGIN_COLORS = {
    "高": PALETTE["success"],
    "中": PALETTE["warning"],
    "低": PALETTE["danger"],
    "高毛利": PALETTE["success"],
    "中毛利": PALETTE["warning"],
    "低毛利": PALETTE["danger"],
}


def render(data: dict, title: str | None = None, width: int = 880, height: int = 260) -> str:
    stages = data.get("stages", [])
    if not stages:
        return f'<div style="color:{PALETTE["muted"]}">（数据缺失）</div>'

    n = len(stages)
    box_w = (width - 60 - (n - 1) * 30) / n
    box_h = 110
    y = 80
    parts = [svg_header(width, height, title)]

    # 流向箭头（先画，再画 box 覆盖）
    for i in range(n - 1):
        x1 = 30 + box_w * (i + 1) + 30 * i - 6
        x2 = 30 + box_w * (i + 1) + 30 * (i + 1) + 6
        ay = y + box_h / 2
        parts.append(
            f'<line x1="{x1}" y1="{ay}" x2="{x2 - 8}" y2="{ay}" '
            f'stroke="{PALETTE["muted"]}" stroke-width="2" marker-end="url(#vc-arrow)"/>'
        )

    # 箭头定义
    parts.insert(1, (
        '<defs><marker id="vc-arrow" markerWidth="10" markerHeight="10" '
        'refX="8" refY="3" orient="auto" markerUnits="strokeWidth">'
        f'<path d="M0,0 L0,6 L9,3 z" fill="{PALETTE["muted"]}"/></marker></defs>'
    ))

    for i, s in enumerate(stages):
        x = 30 + (box_w + 30) * i
        margin = s.get("margin", "中")
        m_color = MARGIN_COLORS.get(margin, PALETTE["muted"])
        items = s.get("items", [])
        # 框
        parts.append(
            f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="10" '
            f'fill="white" stroke="{m_color}" stroke-width="2"/>'
        )
        # 标题
        parts.append(
            f'<text x="{x + box_w/2}" y="{y + 24}" text-anchor="middle" font-size="14" '
            f'font-weight="600" fill="{PALETTE["text"]}">{esc(s.get("name", ""))}</text>'
        )
        # 毛利率标签
        parts.append(
            f'<rect x="{x + box_w/2 - 26}" y="{y + 32}" width="52" height="18" rx="9" '
            f'fill="{m_color}"/>'
        )
        parts.append(
            f'<text x="{x + box_w/2}" y="{y + 45}" text-anchor="middle" font-size="11" '
            f'font-weight="600" fill="white">毛利 {esc(margin)}</text>'
        )
        # items
        text_y = y + 68
        for it in items[:3]:
            parts.append(
                f'<text x="{x + box_w/2}" y="{text_y}" text-anchor="middle" font-size="11" '
                f'fill="{PALETTE["text"]}">• {esc(it)}</text>'
            )
            text_y += 14

    parts.append(svg_footer())
    return "\n".join(parts)
