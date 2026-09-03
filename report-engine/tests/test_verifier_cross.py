"""验证升级：跨来源事实合并 + 权威度加权核实的回归测试。"""

from research.models import Fact, ResearchSource
from research.verifier import verify_facts


def _src(sid: str, q: float) -> ResearchSource:
    return ResearchSource(id=sid, url=f"https://{sid}.example.com", quality_score=q)


def _fact(fid: str, claim: str, category: str, ev: list[str]) -> Fact:
    return Fact(id=fid, claim=claim, category=category, evidence=ev)


def test_numeric_alignment_merges_cross_source_evidence():
    """同一聚合指标、数值相交但表述不同 → 合并来源证据 → 判已核实。"""
    sources = [_src("s1", 0.6), _src("s2", 0.6)]
    facts = [
        _fact("f1", "中国现制咖啡市场规模达 7000 亿元", "市场规模", ["s1"]),
        _fact("f2", "2025 年现制咖啡市场约 7000 亿元", "市场规模", ["s2"]),
    ]
    verify_facts(facts, sources)
    assert facts[0].status == "verified"
    assert facts[1].status == "verified"
    # 互相补全了来源
    assert "s2" in facts[0].evidence and "s1" in facts[1].evidence


def test_numeric_merge_ignores_different_metrics():
    """数值相同但类别不同/非聚合指标 → 不误合并。"""
    sources = [_src("s1", 0.6), _src("s2", 0.6)]
    facts = [
        _fact("f1", "门店数 7000 家", "竞争格局", ["s1"]),
        _fact("f2", "员工 7000 人", "竞争格局", ["s2"]),
    ]
    verify_facts(facts, sources)
    # 非聚合指标，不做数值合并 → 各自单源 → unverified
    assert all(f.status == "unverified" for f in facts)


def test_high_authority_single_source_verified():
    """单源但权威（官方/财报 quality>=0.75）→ 已核实。"""
    sources = [_src("s1", 0.9)]
    facts = [_fact("f1", "国家统计局：集成电路产量同比增长 24.7%", "增速", ["s1"])]
    verify_facts(facts, sources)
    assert facts[0].status == "verified"


def test_low_authority_single_source_unverified():
    """单源且低权威 → 待确认。"""
    sources = [_src("s1", 0.3)]
    facts = [_fact("f1", "某自媒体称市场份额达 30%", "市场规模", ["s1"])]
    verify_facts(facts, sources)
    assert facts[0].status == "unverified"


def test_conflict_detection_still_works():
    """同一类别聚合指标、数值不相交 → 仍标冲突（两种口径）。"""
    sources = [_src("s1", 0.6), _src("s2", 0.6)]
    facts = [
        _fact("f1", "市场规模 7000 亿元", "市场规模", ["s1"]),
        _fact("f2", "市场规模 9750 亿元", "市场规模", ["s2"]),
    ]
    verify_facts(facts, sources)
    assert all(f.status == "conflicted" for f in facts)


def test_no_source_estimate():
    """无来源 → 估算。"""
    sources = [_src("s1", 0.6)]
    facts = [_fact("f1", "市场规模约 7000 亿元", "市场规模", [])]
    verify_facts(facts, sources)
    assert facts[0].status == "estimate"
