"""商业模式画布（9 宫格）。

data 格式：
{
  "key_partners": [...], "key_activities": [...], "value_propositions": [...],
  "customer_relationships": [...], "customer_segments": [...],
  "key_resources": [...], "channels": [...],
  "cost_structure": [...], "revenue_streams": [...]
}
"""
from __future__ import annotations

from ._common import PALETTE, esc, svg_footer, svg_header


def _cell(x, y, w, h, title, items, color):
    parts = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" '
        f'fill="white" stroke="{color}" stroke-width="1.5"/>',
        f'<rect x="{x}" y="{y}" width="{w}" height="28" rx="8" fill="{color}"/>',
        f'<rect x="{x}" y="{y + 18}" width="{w}" height="10" fill="{color}"/>',
        f'<text x="{x + w/2}" y="{y + 19}" text-anchor="middle" font-size="12" '
        f'font-weight="600" fill="white">{esc(title)}</text>',
    ]
    # 列表
    text_y = y + 44
    for item in items[:5]:
        parts.append(
            f'<text x="{x + 12}" y="{text_y}" font-size="11" fill="{PALETTE["text"]}">'
            f'• {esc(item)}</text>'
        )
        text_y += 18
    return "\n".join(parts)


def render(data: dict, title: str | None = None, width: int = 880, height: int = 520) -> str:
    parts = [svg_header(width, height, title)]

    # 9 宫格布局：上排 3 大格 + 中排 1 大 + 下排 2 大
    # 简化：左 5 列（KP/KA/VP/CR/CS） + 中间 2 列（KR/CH） + 右 2 列（CS/$）
    # 直接用三段式经典布局
    layout = [
        # x, y, w, h, title, key, color
        (20,  50, 200, 220, "重要合作 (KP)", "key_partners", PALETTE["primary"]),
        (240, 50, 200, 105, "关键业务 (KA)", "key_activities", PALETTE["primary_light"]),
        (240, 165, 200, 105, "核心资源 (KR)", "key_resources", PALETTE["primary_light"]),
        (460, 50, 220, 220, "价值主张 (VP)", "value_propositions", PALETTE["accent"]),
        (700, 50, 160, 105, "客户关系 (CR)", "customer_relationships", PALETTE["primary_light"]),
        (700, 165, 160, 105, "渠道通路 (CH)", "channels", PALETTE["primary_light"]),
        (20, 290, 200, 200, "客户细分 (CS)", "customer_segments", PALETTE["primary"]),
        (240, 290, 420, 200, "成本结构", "cost_structure", PALETTE["danger"]),
        (680, 290, 220, 200, "收入来源 ($)", "revenue_streams", PALETTE["success"]),
    ]
    for x, y, w, h, t, key, color in layout:
        items = data.get(key) or []
        if isinstance(items, str):
            items = [items]
        parts.append(_cell(x, y, w, h, t, items, color))

    parts.append(svg_footer())
    return "\n".join(parts)
