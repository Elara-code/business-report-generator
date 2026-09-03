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


def truncate_label(s: str, max_chars: int = 10, suffix: str = "…") -> str:
    """单点截断超长标签，避免 SVG 渲染时溢出/重叠。

    规则：
    - None / 空 → 返回空字符串
    - 长度 ≤ max_chars → 原样返回
    - 长度 > max_chars → 截到 max_chars-1 + suffix（中文字符按 1 字算）

    设计取舍（详见 v0.3 设计文档）：
    - 选单点截断而非自动折行，因为 SVG 折行需要 mea sureText + 折行算法，
      实现复杂度高，收益低（95% 标签 < 10 字）。
    - 真正的根因在 LLM 输出，由 prompt 约束更优；这里只是兜底。
    """
    s = str(s or "").strip()
    if not s:
        return ""
    if len(s) <= max_chars:
        return s
    return s[: max(1, max_chars - 1)] + suffix


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


def text_card(title: str | None, lines: list[str], note: str | None = None) -> str:
    """文字说明卡：当图表缺结构化数据、但有文字性结论时，渲染成专业的说明卡，
    而不是裸占位文本「（数据缺失）」。"""
    rows = []
    for ln in lines:
        ln = (ln or "").strip()
        if not ln:
            continue
        rows.append(f'<div style="padding:4px 0;color:#334155;font-size:13px;line-height:1.6">{esc(ln)}</div>')
    if not rows:
        return ""
    body = "".join(rows)
    if note:
        body += f'<div style="margin-top:8px;padding-top:8px;border-top:1px solid #eef2f6;color:#94a3b8;font-size:11px">{esc(note)}</div>'
    head = f'<div style="font-size:13px;font-weight:600;color:#475569;margin-bottom:8px">{esc(title)}</div>' if title else ""
    return (
        f'<div style="padding:16px 18px;border:1px solid #e2e8f0;border-radius:12px;'
        f'background:linear-gradient(180deg,#fafcfe,#f4f7fb)">'
        f'{head}{body}</div>'
    )
