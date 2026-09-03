"""研究流水线包：基于公开信息生成可溯源报告的核心。

模块：
- models.py    证据链领域模型（来源 / 事实 / 步骤 / 计划）
- planner.py   意图解析 + 检索词规划
- searcher.py  检索层（DuckDuckGo 真实搜索 / 离线演示语料）
- extractor.py 事实抽取（LLM / 语料直供 / 兜底）
- verifier.py  交叉验证 + 冲突检测 + 置信度计算
- drafter.py   证据驱动生成（LLM / 离线组装）
- pipeline.py  流水线编排（对外主入口 run_research）
"""
from .models import EvidenceChain, Fact, ResearchLog, ResearchPlan, ResearchSource, ResearchStep
from .planner import build_plan
from .pipeline import run_research
from .searcher import CuratedSearcher, DuckDuckGoSearcher, filter_dedup, get_searcher
from .extractor import extract_facts
from .verifier import verify_facts, compute_confidence
from .drafter import draft_report, attach_evidence

__all__ = [
    "EvidenceChain", "Fact", "ResearchLog", "ResearchPlan", "ResearchSource", "ResearchStep",
    "build_plan", "run_research", "CuratedSearcher", "DuckDuckGoSearcher",
    "filter_dedup", "get_searcher", "extract_facts", "verify_facts",
    "compute_confidence", "draft_report", "attach_evidence",
]
