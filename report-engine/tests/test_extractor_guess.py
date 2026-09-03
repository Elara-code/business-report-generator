"""extractor 兜底：LLM 漏填 source_ids 时的来源猜测匹配测试。"""

from research.extractor import _guess_source_ids
from research.models import ResearchSource


def _src(sid: str, title: str, snippet: str) -> ResearchSource:
    return ResearchSource(id=sid, title=title, url=f"https://{sid}.example.com", snippet=snippet)


def test_guess_by_digit():
    """claim 中的大数字出现在来源摘要 → 绑定该来源。"""
    sources = [
        _src("s1", "咖啡白皮书", "2025年中国现制咖啡市场规模约 1987 亿元"),
        _src("s2", "无关新闻", "今日天气晴"),
    ]
    assert _guess_source_ids("现制咖啡市场规模约1987亿元", sources) == [1]


def test_guess_by_entity_word():
    """无大数字时，实体词 ≥2 命中同一来源 → 绑定。"""
    sources = [
        _src("s1", "星巴克中国战略", "星巴克引入博裕资本，控股权易主，本土化控股"),
        _src("s2", "天气", "晴转多云"),
    ]
    assert _guess_source_ids("星巴克中国引入博裕资本，开启本土化控股模式", sources) == [1]


def test_guess_no_match_returns_empty():
    """无任何匹配 → 返回空，不伪造来源。"""
    sources = [_src("s1", "天气", "晴")]
    assert _guess_source_ids("完全无关的事实描述", sources) == []
