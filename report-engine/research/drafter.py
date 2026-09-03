"""证据驱动生成：只基于已核实的证据链撰写报告正文。

- 真实模式：把"来源编号 + 事实 + 核实状态"注入 Prompt，要求 LLM 只引用事实清单，
  正文量化论断挂 [N] 引用，并输出 Report JSON；
- 离线模式：直接从证据链组装结构化报告（无 LLM 也能端到端演示）。

重要原则：报告中的每个关键数字必须来自证据链；无法核实的用"估算/推断"标注，
绝不要求 LLM 编造来源。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Callable

from .models import EvidenceChain, ResearchPlan
from .verifier import compute_confidence

LLMCallable = Callable[..., str]

TYPE_SUFFIX = {"industry": "行业", "product": "产品", "competitor": "竞品对比"}

# 各报告类型的章节模板（离线组装用）：(章节名, 事实类别)
SECTION_MAP = {
    "industry": [
        ("市场概览", ["市场规模", "增速"]),
        ("价值链与商业模式", ["产业链"]),
        ("竞争格局", ["竞争格局", "头部玩家"]),
        ("趋势、机会与风险", ["趋势", "风险"]),
    ],
    "product": [
        ("产品定位与目标用户", ["定位", "目标用户"]),
        ("核心功能与用户体验", ["核心功能"]),
        ("商业模式与定价", ["商业模式", "定价"]),
        ("增长动态", ["增长"]),
    ],
    "competitor": [
        ("功能与定位对比", ["功能对比", "定位"]),
        ("定价与商业模式对比", ["定价对比", "商业模式"]),
        ("优劣势总结", ["优势", "劣势"]),
    ],
}

# 冲突/待确认事实的渲染提示
STATUS_HINT = {
    "verified": "",
    "unverified": "（单源待确认）",
    "estimate": "（估算）",
    "inference": "（推断）",
    "conflicted": "（口径冲突，见来源说明）",
}


def cite_map(sources) -> dict:
    """source_id -> 引用编号字符串。id 形如 s1 → '1'。"""
    m = {}
    for s in sources:
        n = re.sub(r"\D", "", s.id)
        m[s.id] = n or s.id
    return m


def _cited(claim: str, evidence: list[str], cmap: dict) -> str:
    refs = "".join(f"[{cmap[e]}]" for e in evidence if e in cmap)
    return f"{claim} {refs}".strip()


def _status_of(fact) -> str:
    return fact.status


# ---------------------------------------------------------------------------
# 离线组装（无 LLM）
# ---------------------------------------------------------------------------

def _assemble(plan: ResearchPlan, chain: EvidenceChain) -> dict:
    sources, facts, cmap = chain.sources, chain.facts, cite_map(chain.sources)
    subject = plan.subject
    type_suffix = TYPE_SUFFIX.get(plan.report_type, "分析")

    # 执行摘要：取已核实事实作为结论
    verified = [f for f in facts if f.status == "verified"]
    pool = verified or facts
    summary_lines = [f"本报告基于 {len(sources)} 个公开来源生成，共抽取 {len(facts)} 条关键事实。"]
    for f in pool[:3]:
        summary_lines.append(f"- {_cited(f.claim, f.evidence, cmap)}{STATUS_HINT[f.status]}")
    summary_lines.append(f"涉及的市场、增速与玩家数据均标注来源与核实状态；无法确认的推断单独标注。")
    summary = "\n".join(summary_lines)

    # 分章节（每节都尝试配图）
    sections = []
    sec_no = 0
    for title, cats in SECTION_MAP.get(plan.report_type, SECTION_MAP["industry"]):
        sec_no += 1
        matched = [f for f in facts if f.category in cats]
        if not matched:
            continue
        lines = [f"本节内容来自 {len(set(e for f in matched for e in f.evidence))} 个公开来源："]
        for f in matched:
            lines.append(f"- {_cited(f.claim, f.evidence, cmap)} {STATUS_HINT[f.status]}")
        sections.append({
            "title": title,
            "content": "\n".join(lines),
            "chart": _build_chart(matched, cmap),
        })

    if not sections:
        sections.append({"title": "关键事实与证据", "content": summary, "chart": _build_chart(facts, cmap)})

    return {
        "meta": {
            "title": f"{subject}{type_suffix}分析报告",
            "subject": subject,
            "type": plan.report_type,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        },
        "summary": summary,
        "sections": sections,
        "appendix": {
            "data_sources": [f"{s.title}（{s.domain}）" for s in sources],
            "limitations": ("本报告基于公开网络来源生成，关键数字均标注来源编号；"
                            "「估算/待确认/冲突」内容请以原始来源为准，不作为投资决策依据。"),
        },
    }


def _build_chart(facts, cmap) -> dict | None:
    """从数值事实构造一张 bar 图（用于离线演示）。"""
    try:
        import re as _re
        cand = [f for f in facts if _re.search(r"\d+(?:\.\d+)?\s*[亿万元]?", f.claim)]
        if not cand:
            return None
        f = cand[0]
        nums = _re.findall(r"(\d+(?:\.\d+)?)\s*([亿万元%]?)", f.claim)
        if not nums:
            return None
        values = []
        cats = []
        # 若事实含多个年份+数值，则画时间序列；否则画单点柱
        for v, unit in nums[:6]:
            values.append(float(v))
            cats.append(f"{unit}{len(values)}")
        return {
            "type": "bar",
            "title": f"关键指标（来源 [{cmap[f.evidence[0]]}]）",
            "data": {"categories": cats, "values": values, "unit": " "},
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# LLM 生成（真实模式）
# ---------------------------------------------------------------------------

_DRAFT_SYSTEM = """你是资深商业分析师，擅长撰写结构化、可视化、可追溯的商业分析报告。
你必须严格遵循以下证据纪律：
1. 只能使用"事实清单"中给出的内容；量化数字必须来自事实清单，并标注来源编号；
2. 正文中引用格式为 [N]（N 为来源编号），放在论断末尾，如"2024 年市场规模约 2,510 亿元[1][2]"；
3. 事实清单中标明"估算/待确认/冲突"的内容，正文要明确写"（估算）""（待确认）""（两种口径）"，不得写成确定性结论；
4. 不得编造任何未在事实清单中出现的来源或数据；
5. 输出必须是严格合法的 JSON，不要包含 ```json 或任何额外文字。"""


def _llm_draft(llm: LLMCallable, plan: ResearchPlan, chain: EvidenceChain) -> dict:
    sources, facts, cmap = chain.sources, chain.facts, cite_map(chain.sources)

    src_lines = []
    for s in sources:
        n = cmap[s.id]
        src_lines.append(f"[{n}] {s.title} | {s.domain} | {s.published_at} | {s.source_type}")
    fact_lines = []
    for f in facts:
        refs = ", ".join(cmap[e] for e in f.evidence if e in cmap)
        fact_lines.append(f"- [{f.status}]（来源 {refs}）{f.claim}")

    schema_hint = _report_schema_hint()
    user = (
        f"报告主题：{plan.subject}\n报告类型：{plan.report_type}\n"
        f"研究范围：市场={plan.market}，时间={plan.time_range}，读者={plan.audience}\n\n"
        f"## 事实清单（只允许引用这里的内容）\n" + "\n".join(fact_lines) +
        f"\n\n## 来源清单\n" + "\n".join(src_lines) +
        f"\n\n## 写作要求（必须严格遵守）\n{schema_hint}"
    )
    raw = llm(_DRAFT_SYSTEM, user, json_mode=True)
    text = raw.strip()
    m = re.search(r"\{[\s\S]*\}", text)
    data = json.loads(m.group(0)) if m else json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("draft 输出不是对象")
    return data


def _report_schema_hint() -> str:
    return """
## 报告风格：可视化优先（读者是普通读者，拒绝大段文字）
整份报告必须以图表为主、文字为辅，让读者"看图即懂"。每个章节按下述结构输出：

{
  "meta": {"title": "报告标题", "subject": "主题", "type": "industry|product|competitor"},
  "summary": "120-180 字执行摘要（结论先行，带 [N] 引用，写成短句，不堆数据）",
  "sections": [
    {"title": "章节标题",
     "content": "简短导语（2-3 行，60-120 字，带 [N] 引用）",
     "key_points": ["要点1", "要点2", "要点3", "要点4"],
     "chart": {"type": "...", "title": "...", "data": {...}}}
  ],
  "appendix": {"data_sources": ["来源标题"], "limitations": "局限性说明"}
}

## 每节都必须配 chart（共 8-9 节，仅当该节确实无任何可结构化信息时才允许 type=null，且这种情况尽量少）
### 图表选择指南（按内容匹配最合适的图，把定性信息也结构化）：
- 数值指标 / 规模 / 份额 / 增速 → bar：{"categories":["A","B"],"values":[25,18],"unit":"%"}
- 随时间变化 / 趋势 → line：{"categories":["2024","2025"],"series":[{"name":"规模","values":[100,130]}],"unit":"亿元"}
- 多维度的强弱评估（哪怕只是定性打分 1-5） → radar：{"axes":["效率","成本","体验"],"values":[4,3,2]}
- 产业链 / 价值链环节 → value_chain：{"stages":[{"name":"上游","items":["原材料"],"margin":"高"},{"name":"中游","items":["生产"],"margin":"中"}]}
- 两个维度上定位多个玩家 / 情景 → matrix：{"x_label":"X","y_label":"Y","points":[{"name":"产品A","x":4,"y":3}]}
- 商业模式 / 能力要素拆解 → canvas：{"key_partners":[...],"key_activities":[...],"value_propositions":[...],"customer_relationships":[...],"key_resources":[...],"channels":[...],"customer_segments":[...],"cost_structure":[...],"revenue_streams":[...]}
- 转化 / 漏斗流程 → funnel：{"stages":[{"name":"访问","value":1000},{"name":"注册","value":300}]}
### chart.data 纪律：
- 数值必须来自事实清单，禁止编造；
- 定性评估（radar/matrix/canvas）的分值或条目须源自事实内容，并在 data 里用 "note"/"说明" 标注"定性评估"；
- 实在无法结构化时，data 里放 {"note": "一句话说明"} 即可，渲染端会显示成说明卡。

## content 与 key_points 纪律：
- content 只写简短导语，禁止长段落；
- key_points 每节 3-5 条，每条一行、≤30 字，把正文里所有量化论断挂 [N] 引用；
- 事实清单中标"估算/待确认/冲突"的内容，明确写"（估算）""（待确认）""（两种口径）"，不得写成确定结论。
"""


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def draft_report(plan: ResearchPlan, chain: EvidenceChain,
                 llm: LLMCallable | None = None) -> dict:
    """返回 Report 原始 dict（随后由 coerce_report 校验补全）。"""
    if llm is not None:
        try:
            raw = _llm_draft(llm, plan, chain)
            # 强制覆盖关键 meta，防止 LLM 跑偏
            raw.setdefault("meta", {})
            raw["meta"]["type"] = plan.report_type
            raw["meta"]["subject"] = plan.subject
            return raw
        except Exception:
            pass  # LLM 失败回退离线组装，保证可用性
    return _assemble(plan, chain)


def attach_evidence(raw: dict, chain: EvidenceChain) -> dict:
    """把证据链与可计算置信度挂到 Report 上。"""
    raw["evidence"] = chain.model_dump()
    raw.setdefault("meta", {})
    raw["meta"]["confidence"] = compute_confidence(chain.facts)
    return raw
