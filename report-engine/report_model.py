"""Pydantic 模型 —— 报告结构的运行时校验。

LLM 输出可能字段缺失、字段拼错、类型错误，必须在校验层兜底。
v0.3 新增：置信度评分模型。
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# 置信度
# ---------------------------------------------------------------------------

ConfidenceLevel = Literal["high", "medium", "low", "unknown"]
"""
high   —— LLM 自评数据可信，且数据源/局限性都有交代
medium —— 有数据但存在估算 / 时效问题
low    —— LLM 自评大量依赖推断 / 知识盲区
unknown —— LLM 未给出置信度（默认）
"""


class ConfidenceInfo(BaseModel):
    """报告级置信度（v0.3 新增）。

    设计目标：让用户立刻知道"这份报告能不能拿去做投资决策"。
    """

    level: ConfidenceLevel = "unknown"
    score: float = Field(default=0.5, ge=0.0, le=1.0,
                         description="0-1 之间，越高越可信")
    reasoning: str = Field(default="", description="LLM 自评依据，1-2 句话")
    factors: list[str] = Field(default_factory=list,
                                description="影响置信度的关键因素（事实/估算/推断/AI 判断）")
    data_cutoff: str = Field(default="", description="LLM 知识截止时间")
    recommended_use: str = Field(default="", description="建议用途（仅供快速浏览/可作决策参考/可直接用于投资）")

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

class ReportMeta(BaseModel):
    title: str = ""
    subject: str = ""
    type: Literal["industry", "product", "competitor"] = "industry"
    generated_at: str = ""
    confidence: Optional[ConfidenceInfo] = None  # v0.3 新增

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

ChartType = Literal["bar", "line", "radar", "canvas", "funnel", "value_chain", "matrix", "null"]


class Chart(BaseModel):
    type: ChartType = "null"
    title: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Section
# ---------------------------------------------------------------------------

class Section(BaseModel):
    title: str
    content: str = ""
    chart: Optional[Chart] = None

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Appendix
# ---------------------------------------------------------------------------

class Source(BaseModel):
    """数据源引用 —— P1 阶段扩展字段，预留位置。"""

    name: str
    url: Optional[str] = None
    published_at: Optional[str] = None
    source_type: Optional[str] = None  # 财报 / 调研 / 新闻 / AI 推断

    model_config = {"extra": "allow"}


class Appendix(BaseModel):
    data_sources: list[Any] = Field(default_factory=list)  # 接受 str 或 Source 字典
    limitations: str = ""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Report (top-level)
# ---------------------------------------------------------------------------

class Report(BaseModel):
    meta: ReportMeta = Field(default_factory=ReportMeta)
    summary: str = ""
    sections: list[Section] = Field(default_factory=list)
    appendix: Appendix = Field(default_factory=Appendix)

    model_config = {"extra": "allow"}

    @field_validator("sections")
    @classmethod
    def _sections_not_empty(cls, v: list[Section]) -> list[Section]:
        if not v:
            raise ValueError("报告至少需要 1 个章节")
        return v


# ---------------------------------------------------------------------------
# 工具方法
# ---------------------------------------------------------------------------

def coerce_report(raw: Any, report_type: str, subject: str, *,
                  force_subject: bool = True) -> Report:
    """将 LLM 原始输出 + 用户输入 强转成 Report。

    规则：
    1. 缺失字段自动补默认值
    2. type 强制覆盖为用户请求的类型（防止 preset 错配）
    3. subject 默认强制覆盖（force_subject=True）；设为 False 时仅在 LLM 返回为空时覆盖
    4. 数据源允许是 str 或 dict，统一转 str 渲染
    """
    if not isinstance(raw, dict):
        raise ValueError(f"LLM 输出不是 dict: {type(raw).__name__}")

    # 强制覆盖 type / subject
    raw.setdefault("meta", {})
    if not isinstance(raw["meta"], dict):
        raw["meta"] = {}
    raw["meta"]["type"] = report_type
    if force_subject or not raw["meta"].get("subject"):
        raw["meta"]["subject"] = subject
    if not raw["meta"].get("title"):
        raw["meta"]["title"] = f"{subject}分析报告"
    if not raw["meta"].get("generated_at"):
        from datetime import datetime
        raw["meta"]["generated_at"] = datetime.now().isoformat(timespec="seconds")

    # 补全顶层默认值
    raw.setdefault("summary", "")
    raw.setdefault("sections", [])
    raw.setdefault("appendix", {"data_sources": [], "limitations": ""})

    return Report.model_validate(raw)
