"""SVG 模板统一入口：按 chart_type 路由。

设计要点（v3.1 修复）：
- LLM 起草报告时对 chart.data 的字段往往不遵循严格 schema（可能用中文 key、
  字符串列表、或只有文字性结论而无结构化数值）。若直接丢给 SVG 模板，会出现
  「图表渲染失败 / （数据缺失）/（无点位）/（轴缺失）」等裸占位甚至崩溃。
- 因此这里统一做两层处理：
  1. normalize：把 LLM 的多种形态映射到各模板期望字段；
  2. fallback：若仍无结构化数据、但 data 里含文字性结论（note/说明/方向/口径等），
     渲染成专业的「文字说明卡」；连文字都没有则返回空（不渲染任何占位）。
"""
from __future__ import annotations

from . import bar, canvas, funnel, line, matrix, radar, value_chain
from ._common import text_card

DISPATCH = {
    "bar": bar.render,
    "line": line.render,
    "radar": radar.render,
    "canvas": canvas.render,
    "funnel": funnel.render,
    "value_chain": value_chain.render,
    "matrix": matrix.render,
}


# ---------------------------------------------------------------------------
# 数据规范化：把 LLM 输出形态映射到模板字段
# ---------------------------------------------------------------------------

def _as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        return [v] if v.strip() else []
    return []


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("，", ""))
    except (TypeError, ValueError):
        return None


def _norm_bar(data) -> tuple[dict, list[str]]:
    """期望 categories/values/unit；支持 items:[{label,value}]、labels/values、{label:value}"""
    out, fallback = {"categories": [], "values": [], "unit": ""}, []
    if not isinstance(data, dict):
        return out, fallback
    unit = str(data.get("unit") or "")
    cats, vals = [], []
    items = _as_list(data.get("items")) or _as_list(data.get("rows"))
    if items and isinstance(items[0], dict):
        for it in items:
            if not isinstance(it, dict):
                continue
            label = it.get("label") or it.get("name") or it.get("category") or it.get("x")
            val = it.get("value") if it.get("value") is not None else it.get("val")
            if label is not None and val is not None:
                cats.append(str(label))
                vals.append(_num(val))
    if not cats:
        cand = _as_list(data.get("categories")) or _as_list(data.get("labels")) or _as_list(data.get("names"))
        vcand = _as_list(data.get("values")) or _as_list(data.get("data"))
        if len(cand) == len(vcand):
            cats, vals = [str(c) for c in cand], [_num(v) for v in vcand]
    if not cats and isinstance(data, dict):
        # {label: value} 形态
        for k, v in data.items():
            if k in ("unit", "note", "title", "type", "items", "rows", "labels", "values"):
                continue
            if _num(v) is not None:
                cats.append(k)
                vals.append(_num(v))
    out = {"categories": cats, "values": vals, "unit": unit}
    if not cats:
        fallback = _text_lines(data)
    return out, fallback


def _norm_line(data) -> tuple[dict, list[str]]:
    """期望 categories/series:[{name,values}]/unit；支持 labels/values"""
    out, fallback = {"categories": [], "series": [], "unit": ""}, []
    if not isinstance(data, dict):
        return out, fallback
    cats = _as_list(data.get("categories")) or _as_list(data.get("labels"))
    unit = str(data.get("unit") or "")
    series = []
    raw_series = data.get("series")
    if isinstance(raw_series, list):
        for s in raw_series:
            if isinstance(s, dict) and _as_list(s.get("values")):
                series.append({"name": s.get("name", "序列"), "values": [_num(v) for v in _as_list(s.get("values"))]})
    elif raw_series is None and _as_list(data.get("values")):
        series = [{"name": "数值", "values": [_num(v) for v in _as_list(data.get("values"))]}]
    out = {"categories": cats, "series": series, "unit": unit}
    if not cats or not series:
        fallback = _text_lines(data)
    return out, fallback


def _norm_radar(data) -> tuple[dict, list[str]]:
    """期望 axes/values 或 axes/series；支持 dimensions"""
    out, fallback = {"axes": [], "values": [], "series": []}, []
    if not isinstance(data, dict):
        return out, fallback
    axes = _as_list(data.get("axes")) or _as_list(data.get("dimensions")) or _as_list(data.get("labels"))
    values = [_num(v) for v in _as_list(data.get("values"))]
    out = {"axes": axes, "values": values}
    if not axes:
        fallback = _text_lines(data)
    elif not values and not data.get("series"):
        # 只有维度没有量化值：降级为文字卡（维度列表）
        fallback = axes + _text_lines(data)
    return out, fallback


def _norm_matrix(data) -> tuple[dict, list[str]]:
    """期望 x_label/y_label/points:[{name,x,y}]；支持 scenarios 文字场景"""
    out, fallback = {"x_label": "X", "y_label": "Y", "points": []}, []
    if not isinstance(data, dict):
        return out, fallback
    out = {
        "x_label": data.get("x_label") or data.get("axis_x") or "X",
        "y_label": data.get("y_label") or data.get("axis_y") or "Y",
        "points": _as_list(data.get("points")),
    }
    if out["points"]:
        pts = []
        for p in out["points"]:
            if isinstance(p, dict) and p.get("x") is not None and p.get("y") is not None:
                pts.append({"name": p.get("name", ""), "x": p.get("x"), "y": p.get("y")})
        out["points"] = pts
    if not out["points"]:
        # scenarios / 场景：文字性结论 → 说明卡
        scenarios = _as_list(data.get("scenarios")) or _as_list(data.get("scenes"))
        fallback = scenarios + _text_lines(data)
    return out, fallback


def _norm_value_chain(data) -> tuple[dict, list[str]]:
    """期望 stages:[{name,items,margin}]；支持 stages 为字符串列表"""
    out, fallback = {"stages": []}, []
    if not isinstance(data, dict):
        return out, fallback
    stages = _as_list(data.get("stages"))
    if stages and isinstance(stages[0], str):
        # 字符串列表 → 每个节点只有名称
        stages = [{"name": s} for s in stages]
    out = {"stages": stages}
    if not stages:
        fallback = _text_lines(data)
    return out, fallback


# canvas 中文 key → 模板 key
_CANVAS_ALIAS = {
    "key_partners": ["key_partners", "重要合作", "合作", "kp"],
    "key_activities": ["key_activities", "关键业务", "业务", "ka", "技能方向"],
    "value_propositions": ["value_propositions", "价值主张", "vp"],
    "customer_relationships": ["customer_relationships", "客户关系", "cr"],
    "customer_segments": ["customer_segments", "客户细分", "客户", "cs"],
    "key_resources": ["key_resources", "核心资源", "kr"],
    "channels": ["channels", "渠道通路", "渠道", "ch"],
    "cost_structure": ["cost_structure", "成本结构", "成本"],
    "revenue_streams": ["revenue_streams", "收入来源", "收入", "$"],
}
_CANVAS_KEYS = list(_CANVAS_ALIAS.keys())


def _norm_canvas(data) -> tuple[dict, list[str]]:
    """期望 9 个英文 key；支持中文 key 映射。全空或格子过少时降级文字卡。"""
    out, fallback = {}, []
    if not isinstance(data, dict):
        return out, fallback
    for key in _CANVAS_KEYS:
        v = None
        for alias in _CANVAS_ALIAS[key]:
            if alias in data and data[alias]:
                v = data[alias]
                break
        if v is not None:
            out[key] = _as_list(v)
    # 少于 3 格有内容时画 9 宫格会大片空白，降级为文字卡
    if sum(1 for v in out.values() if v) >= 3:
        return out, fallback
    # 降级：从 data 里找一组列表当「关键信息」展示
    for k, v in data.items():
        lst = _as_list(v)
        if lst and all(not isinstance(x, dict) for x in lst):
            fallback = [f"{k}：{'；'.join(str(x) for x in lst[:6])}"]
            break
    fallback += _text_lines(data)
    return {}, fallback


def _text_lines(data: dict) -> list[str]:
    """从 data 中提取文字性结论，作为说明卡内容。"""
    if not isinstance(data, dict):
        return []
    lines = []
    for key in ("方向", "结论", "note", "说明", "口径", "来源", "注意", "总结", "观点"):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            label = key if key in ("方向", "结论", "观点", "说明") else ""
            lines.append(f"{('' if not label else label + '：')}{v.strip()}")
    # 兜底：把字符串值都收进来
    for k, v in data.items():
        if isinstance(v, str) and v.strip() and not any(v.strip() == (l.split("：", 1)[-1]) for l in lines):
            lines.append(v.strip())
    return lines


_NORM = {
    "bar": _norm_bar,
    "line": _norm_line,
    "radar": _norm_radar,
    "matrix": _norm_matrix,
    "value_chain": _norm_value_chain,
    "canvas": _norm_canvas,
    "funnel": _norm_bar,  # funnel 也按类 bar 处理（categories/values）
}


def render_chart(chart_type: str | None, data: dict, title: str | None = None) -> str:
    if not chart_type or chart_type == "null":
        return ""
    fn = DISPATCH.get(chart_type)
    if not fn:
        return f'<div style="color:#64748b">（未知图表类型: {chart_type}）</div>'

    # 1) data 非 dict 时先兜底（LLM 可能输出字符串/列表）
    if not isinstance(data, dict):
        data = {"note": str(data)} if str(data).strip() else {}

    # 2) 规范化
    norm = _NORM.get(chart_type)
    if norm:
        ndata, fallback = norm(data)
        if not fallback and ndata:
            try:
                return fn(ndata, title=title)
            except Exception:
                fallback = _text_lines(data)
        # 3) 降级：文字说明卡
        if fallback:
            return text_card(title, fallback)
        return ""
    try:
        return fn(data, title=title)
    except Exception:
        lines = _text_lines(data)
        return text_card(title, lines) if lines else ""
