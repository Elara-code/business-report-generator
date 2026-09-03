"""研究流水线领域模型：来源 / 事实 / 步骤日志 / 证据链。

这是"基于公开信息 + 专业精准"的核心数据层：
- ResearchSource：一条可追溯的公开来源（URL / 发布时间 / 机构 / 类型）
- Fact：一条关键事实，绑定来源编号与核实状态（已核实/待确认/冲突/估算/推断）
- EvidenceChain：来源 + 事实 + 流水线日志的聚合，随报告一起持久化
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

# 来源类型：官方数据 / 行业报告 / 公司财报 / 新闻报道 / 自媒体 / 其他
SourceType = Literal["official", "report", "financial", "news", "media", "other"]

# 事实核实状态
FactStatus = Literal["verified", "conflicted", "unverified", "estimate", "inference"]
# verified    —— 多源交叉验证一致（至少 2 个独立来源）
# conflicted  —— 不同来源口径不一致，需同时展示
# unverified  —— 仅单一来源，待二次确认
# estimate    —— 无直接来源，为合理估算
# inference   —— 由已核实事实推出的分析判断

# 流水线步骤状态
StepStatus = Literal["pending", "running", "done", "issue", "error"]

# 步骤展示名（与前端"分析过程"面板对应）
STEP_NAMES = [
    "理解分析任务",   # parse
    "公开网络检索",   # search
    "来源筛选与去重",  # filter
    "事实抽取",       # extract
    "交叉验证",       # verify
    "证据驱动生成",   # draft
    "渲染与导出",     # render
]


def now_cn() -> str:
    """当前北京时间 ISO 字符串。"""
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


class ResearchSource(BaseModel):
    """一条公开来源。id 形如 s1, s2 ... 与报告引用 [1][2] 对应（按序号）。"""

    id: str = ""
    title: str = ""
    url: str = ""
    snippet: str = ""
    domain: str = ""
    published_at: str = ""          # 发布时间（尽力从检索结果解析）
    source_type: SourceType = "other"
    accessed_at: str = ""           # 抓取时间
    quality_score: float = Field(default=0.5, ge=0.0, le=1.0)  # 权威度启发式评分
    seed_facts: list["Fact"] = Field(default_factory=list)  # 演示语料直供的事实（离线模式）


class Fact(BaseModel):
    """一条关键事实（论断级证据）。"""

    id: str = ""
    claim: str = ""
    status: FactStatus = "unverified"
    category: str = ""              # 市场规模 / 增速 / 玩家 / 定价 ...
    evidence: list[str] = Field(default_factory=list)  # 支撑该事实的来源 id 列表
    note: str = ""


class ResearchStep(BaseModel):
    """流水线单步状态。"""

    name: str = ""
    status: StepStatus = "pending"
    message: str = ""
    detail: str = ""


class ResearchLog(BaseModel):
    """流水线运行日志。"""

    steps: list[ResearchStep] = Field(default_factory=list)
    started_at: str = ""
    elapsed_ms: int = 0


class ResearchPlan(BaseModel):
    """研究意图：解析后的任务参数（用户未输入时使用默认值）。"""

    report_type: str = "industry"
    subject: str = ""
    market: str = "全国"            # 默认：全国
    time_range: str = "近1年"        # 默认：近 1 年
    audience: str = "普通读者"        # 默认：普通读者
    queries: list[str] = Field(default_factory=list)
    display: str = ""               # 如 "行业分析 · 市场：全国 · 时间范围：近1年 · 读者：普通读者"


class EvidenceChain(BaseModel):
    """证据链：一次研究产生的全部可追溯证据。"""

    plan: ResearchPlan = Field(default_factory=ResearchPlan)
    sources: list[ResearchSource] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    log: ResearchLog = Field(default_factory=ResearchLog)
