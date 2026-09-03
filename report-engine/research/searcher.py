"""检索层：Searcher 接口 + 真实搜索（DuckDuckGo，无需 Key）+ 离线演示语料。

设计目标：
- 真实模式：DuckDuckGo 免费 Web 搜索，无需 API Key，网络可用时返回真实公开来源；
- 离线模式：CuratedSearcher 从本地演示语料（research/corpus/*.json）返回来源，
  保证无网 / 无 Key 时整条研究流水线仍可端到端演示；
- get_searcher() 自动降级：优先 DDG，失败回退 Curated 并给出 warning。
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlparse

from .models import ResearchSource, now_cn

HERE = os.path.dirname(os.path.abspath(__file__))


@dataclass
class SearchResult:
    """检索原始结果（未定标来源模型前的中转结构）。"""

    title: str
    url: str
    snippet: str = ""
    published_at: str = ""
    facts: list[dict] = field(default_factory=list)  # 演示语料直供事实 [{claim,category}]


class Searcher(Protocol):
    name: str

    def search(self, query: str, limit: int = 8) -> list[SearchResult]: ...


# ---------------------------------------------------------------------------
# DuckDuckGo 真实搜索
# ---------------------------------------------------------------------------

class DuckDuckGoSearcher:
    """DuckDuckGo Web 搜索（免费、无需 API Key）。

    依赖 ddgs（或旧版 duckduckgo_search）。导入失败 / 网络失败时抛出，
    由 get_searcher() 捕获并回退到演示语料。
    """

    name = "duckduckgo"

    def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS  # 旧包名兼容
        out: list[SearchResult] = []
        with DDGS() as ddgs:
            for row in ddgs.text(query, max_results=limit):
                title = str(row.get("title", "") or "")
                url = str(row.get("href", "") or "")
                if not url or not title:
                    continue
                out.append(SearchResult(
                    title=title,
                    url=url,
                    snippet=str(row.get("body", "") or "")[:500],
                    published_at=str(row.get("published", "") or ""),
                ))
        return out


# ---------------------------------------------------------------------------
# 离线演示语料（Curated）
# ---------------------------------------------------------------------------

class CuratedSearcher:
    """从本地演示语料返回"来源"，用于离线/无 Key 时演示整条流水线。

    语料文件结构（research/corpus/<preset>.json）：
    {
      "keywords": ["咖啡", "现制咖啡"],
      "sources": [
        {
          "title": "...", "url": "...", "domain": "...", "published_at": "...",
          "source_type": "report", "snippet": "...",
          "facts": [{"claim": "...", "category": "市场规模"}]
        }
      ]
    }
    注意：这是**演示语料**，不代表真实检索结果；真实模式请使用 DuckDuckGoSearcher。
    """

    name = "curated"

    def __init__(self, corpus_dir: str | None = None):
        self.corpus_dir = corpus_dir or os.path.join(HERE, "corpus")
        self._records: list[tuple[list[str], dict]] = self._load()

    def _load(self) -> list[tuple[list[str], dict]]:
        records: list[tuple[list[str], dict]] = []
        if not os.path.isdir(self.corpus_dir):
            return records
        for fname in sorted(os.listdir(self.corpus_dir)):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.corpus_dir, fname), "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            kws = [str(k) for k in data.get("keywords", [])]
            for src in data.get("sources", []):
                if isinstance(src, dict) and src.get("url"):
                    records.append((kws, src))
        return records

    def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        q_tokens = set(re.findall(r"[\w\u4e00-\u9fff]+", query.lower()))
        scored: list[tuple[int, dict]] = []
        for kws, src in self._records:
            kw_set = {str(k).lower() for k in kws}
            # 子串匹配：查询 token 与关键词互相包含即命中（应对 CJK 连续分词差异）
            hit = sum(1 for t in q_tokens if any(k in t or t in k for k in kw_set))
            if hit > 0:
                scored.append((hit, src))
        scored.sort(key=lambda x: (-x[0], str(x[1].get("published_at", ""))))
        results: list[SearchResult] = []
        for _, src in scored[:limit]:
            results.append(SearchResult(
                title=str(src.get("title", "")),
                url=str(src.get("url", "")),
                snippet=str(src.get("snippet", "")),
                published_at=str(src.get("published_at", "")),
                facts=src.get("facts", []) or [],
            ))
        return results


# ---------------------------------------------------------------------------
# 来源筛选与去重
# ---------------------------------------------------------------------------

# 来源类型权威度权重（越高越可信）
_TYPE_WEIGHT = {
    "official": 1.0,   # 官方数据 / 政府
    "report": 0.85,    # 行业报告 / 咨询机构
    "financial": 0.9,  # 公司财报 / 交易所
    "news": 0.6,       # 正规新闻媒体
    "media": 0.3,      # 自媒体 / 社区
    "other": 0.4,
}

# 按域名关键词提升权威度（覆盖政府/权威研究机构/主流财经与新闻媒体）
_AUTHORITY_HINTS = [
    # 政府 / 官方数据
    ("stats.gov.cn", "official"), ("gov.cn", "official"), ("miit.gov.cn", "official"),
    ("mofcom.gov.cn", "official"), ("ndrc.gov.cn", "official"), ("samr.gov.cn", "official"),
    ("mca.gov.cn", "official"), ("customs.gov.cn", "official"),
    # 权威研究机构 / 行业报告 / 咨询
    ("ccfa", "report"), ("iresearch", "report"), ("questmobile", "report"),
    ("caict.ac.cn", "report"), ("askci", "report"), ("chinabaogao", "report"),
    ("iiMedia", "report"), ("deloitte", "report"), ("pwc", "report"), ("kpmg", "report"),
    ("mckinsey", "report"), ("bain", "report"), ("bcg", "report"), ("euromonitor", "report"),
    ("statista", "report"), ("gartner", "report"), ("idc.com", "report"),
    ("counterpoint", "report"), ("canalys", "report"), ("mintel", "report"),
    ("iimedia", "report"), ("vzkoo", "report"), ("report", "report"),
    # 财经 / 财报 / 交易所
    ("eastmoney", "financial"), ("finance", "financial"), ("annualreport", "financial"),
    ("cfo", "financial"), ("cls.cn", "financial"), ("yicai", "financial"),
    ("caixin", "financial"), ("wallstreetcn", "financial"), ("xueqiu", "financial"),
    ("10jqka", "financial"), ("stockstar", "financial"), ("stcn.com", "financial"),
    ("luckincoffee", "financial"), ("investor.", "financial"), ("annualreports", "financial"),
    # 主流新闻媒体
    ("people.com", "news"), ("xinhuanet", "news"), ("chinadaily", "news"),
    ("cctv.com", "news"), ("thepaper", "news"), ("ifeng", "news"),
    ("chinanews", "news"), ("news", "news"), ("sina", "news"),
    ("163.com", "news"), ("qq.com", "news"), ("36kr", "news"), ("jiemian", "news"),
    ("21jingji", "news"), ("nbd.com", "news"), ("zaker", "news"),
    # 自媒体 / 社区（低权威）
    ("mp.weixin", "media"), ("zhihu", "media"), ("xiaohongshu", "media"),
    ("toutiao.com", "media"), ("sohu.com", "media"), ("baike.baidu.com", "media"),
]

# 明显无关 / 广告 / 工具类域名黑名单（DDG 常混入，直接剔除）
_BLOCKED_DOMAINS = {
    "wolframalpha.com", "acura.com", "galvion.com", "amazon.com", "amazon.cn",
    "ebay.com", "aliexpress.com", "pinterest.com", "instagram.com", "facebook.com",
    "youtube.com", "tiktok.com", "wikipedia.org", "britannica.com", "sparknotes.com",
    "hubspot.com", "salesforce.com", "microsoft.com", "apple.com", "opensubtitles.org",
    "linkedin.com", "lexology.com", "slideshare.net", "scribd.com", "issuu.com",
}

# 按报告类型的"垂直权威源"加权（域名关键词 → quality 加分）。
# 命中垂直领域的权威站点（行业报告站/财经数据站/官方）额外加分，让检索结果更聚焦专业来源。
_VERTICAL_BONUS: dict[str, dict[str, float]] = {
    "industry": {
        "iresearch": 0.1, "askci": 0.1, "chinabaogao": 0.1, "iimedia": 0.1,
        "ccfa": 0.1, "qianzhan": 0.1, "guanyan": 0.1, "sinoir": 0.1,
        "report": 0.05, "baogao": 0.05, "zhiyan": 0.05, "huaon": 0.05,
        "gov.cn": 0.1, "stats": 0.1, "caict": 0.1,
    },
    "product": {
        "apple.com": 0.08, "google": 0.08, "microsoft": 0.08, "notion": 0.08,
        "obsidian": 0.08, "official": 0.05, "developer": 0.05, "docs": 0.03,
        "producthunt": 0.05, "appstore": 0.05,
    },
    "competitor": {
        "comparison": 0.08, "versus": 0.08, "review": 0.05, "评测": 0.05,
        "zol.com.cn": 0.05, "producthunt": 0.05, "community": 0.03,
    },
}

# 同一域名最多保留的来源数（防止单一权威站霸占名额，保证来源多样性）
_MAX_PER_DOMAIN = 2


def _infer_source_type(url: str, hint: str | None = None) -> str:
    if hint and hint in _TYPE_WEIGHT:
        return hint
    host = (url or "").lower()
    for key, stype in _AUTHORITY_HINTS:
        if key in host:
            return stype
    return "other"


def _quality(url: str, source_type: str, has_snippet: bool, has_date: bool) -> float:
    base = _TYPE_WEIGHT.get(source_type, 0.4)
    if has_snippet:
        base += 0.1
    if has_date:
        base += 0.05
    return round(min(base, 1.0), 2)


def filter_dedup(results: list[SearchResult], max_sources: int = 12,
                 source_type_hint: dict[str, str] | None = None,
                 vertical_bonus: dict[str, float] | None = None) -> list[ResearchSource]:
    """去重（按 URL 归一化）、垂直源加权、排序（权威度 + 时效）、截断。"""
    hint_map = source_type_hint or {}
    bonus_map = vertical_bonus or {}
    seen: set[str] = set()
    out: list[ResearchSource] = []
    for i, r in enumerate(results, 1):
        url = (r.url or "").strip()
        if not url:
            continue
        host = (urlparse(url).netloc or "").lower()
        if any(b in host for b in _BLOCKED_DOMAINS):
            continue  # 剔除无关/广告/工具类域名
        norm = re.sub(r"[?#].*$", "", url).rstrip("/").lower()
        if norm in seen:
            continue
        seen.add(norm)
        stype = _infer_source_type(url, hint_map.get(url))
        has_snippet = bool(r.snippet.strip())
        has_date = bool(r.published_at.strip())
        quality = _quality(url, stype, has_snippet, has_date)
        # 垂直权威源加权：域名命中报告类型对应的权威源则加分
        for kw, b in bonus_map.items():
            if kw in host:
                quality = min(quality + b, 1.0)
                break
        src = ResearchSource(
            id=f"s{i}",
            title=r.title,
            url=url,
            snippet=r.snippet,
            domain=urlparse(url).netloc,
            published_at=r.published_at,
            source_type=stype,  # type: ignore[arg-type]
            accessed_at=now_cn(),
            quality_score=round(quality, 2),
            seed_facts=r.facts or [],
        )
        out.append(src)

    # 按权威度 + 有无摘要 排序，保留顺序稳定
    out.sort(key=lambda s: s.quality_score, reverse=True)

    # 域名多样性：同一域名最多保留 _MAX_PER_DOMAIN 个
    final: list[ResearchSource] = []
    domain_count: dict[str, int] = {}
    for s in out:
        d = (s.domain or "").lower()
        if domain_count.get(d, 0) >= _MAX_PER_DOMAIN:
            continue
        domain_count[d] = domain_count.get(d, 0) + 1
        final.append(s)
    return final[:max_sources]


# ---------------------------------------------------------------------------
# 工厂
# ---------------------------------------------------------------------------

def get_searcher(prefer: str = "auto", corpus_dir: str | None = None) -> tuple[Searcher, str]:
    """返回 (searcher, warning)。prefer: auto | curated | duckduckgo。"""
    if prefer == "curated":
        return CuratedSearcher(corpus_dir), "curated（离线演示语料）"
    try:
        ddg = DuckDuckGoSearcher()
        # 探测一次，确认网络可用
        probe = ddg.search("test", limit=1)
        if probe or True:  # 不强制返回结果，仅确认未抛异常
            return ddg, ""
    except Exception:
        pass
    return CuratedSearcher(corpus_dir), "duckduckgo 不可用，已回退到离线演示语料"
