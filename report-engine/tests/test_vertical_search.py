"""检索源垂直化测试：查询构造、垂直权威源加权、来源域名多样性。"""

from research.planner import build_plan
from research.searcher import SearchResult, filter_dedup


def _res(url: str, title: str = "标题", snippet: str = "内容摘要") -> SearchResult:
    return SearchResult(title=title, url=url, snippet=snippet)


def test_industry_queries_contain_year_and_authority():
    """行业查询应注入当前年份与权威词。"""
    plan = build_plan("industry", "咖啡")
    joined = " ".join(plan.queries)
    assert "市场规模" in joined
    assert any(y in joined for y in ("2025", "2026", "2027"))  # 当年年份
    assert "行业报告" in joined


def test_competitor_queries_compare_names():
    """竞品查询应包含对比词与双方名字。"""
    plan = build_plan("competitor", "Notion vs Obsidian")
    joined = " ".join(plan.queries)
    assert "Notion" in joined and "Obsidian" in joined
    assert "对比" in joined or "差异" in joined


def test_vertical_bonus_raises_authority():
    """垂直权威源（行业报告站）在 industry 场景下应获得 quality 加分。"""
    r1 = _res("https://www.iresearch.cn/report/coffee.html", "艾瑞报告", "市场规模数据")
    r2 = _res("https://blog.example.com/coffee.html", "个人博客", "市场规模数据")
    srcs = filter_dedup([r1, r2], max_sources=12,
                        vertical_bonus={"iresearch": 0.1})
    by_url = {s.url: s for s in srcs}
    assert by_url[r1.url].quality_score > by_url[r2.url].quality_score


def test_domain_diversity_limit():
    """同一域名最多保留 2 个来源。"""
    results = [_res(f"https://report.baidu.com/p{i}", f"报告{i}", "内容") for i in range(5)]
    srcs = filter_dedup(results, max_sources=12)
    domains = [s.domain for s in srcs]
    assert domains.count("report.baidu.com") <= 2
