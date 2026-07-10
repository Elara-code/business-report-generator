"""通用 SVG 工具：颜色板、文本宽度估算、viewBox 构造等。"""
from __future__ import annotations

import html

# 主题色板（light theme），所有图表保持一致
PALETTE = {
    "primary": "#2563eb",       # 深蓝
    "primary_light": "#60a5fa",
    "primary_lighter": "#dbeafe",
    "accent": "#f97316",        # 橘
    "accent_light": "#fed7aa",
    "success": "#10b981",       # 绿
    "warning": "#f59e0b",       # 黄
    "danger": "#ef4444",        # 红
    "purple": "#8b5cf6",
    "pink": "#ec4899",
    "text": "#0f172a",
    "muted": "#64748b",
    "border": "#e2e8f0",
    "bg": "#f8fafc",
    "white": "#ffffff",
}

SERIES_COLORS = [
    PALETTE["primary"],
    PALETTE["accent"],
    PALETTE["success"],
    PALETTE["purple"],
    PALETTE["pink"],
    PALETTE["warning"],
    PALETTE["danger"],
    PALETTE["primary_light"],
]


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def text_width(s: str, size: int = 12, ratio: float = 0.6) -> float:
    """粗略估算单行文本宽度（用于排版）。"""
    return len(str(s)) * size * ratio


def svg_header(width: int, height: int, title: str | None = None) -> str:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" height="auto" font-family="-apple-system, BlinkMacSystemFont, '
        f'\'PingFang SC\', \'Hiragino Sans GB\', \'Microsoft YaHei\', sans-serif">'
    ]
    if title:
        parts.append(
            f'<text x="{width//2}" y="24" text-anchor="middle" font-size="16" '
            f'font-weight="600" fill="{PALETTE["text"]}">{esc(title)}</text>'
        )
    return "\n".join(parts)


def svg_footer() -> str:
    return "</svg>"
