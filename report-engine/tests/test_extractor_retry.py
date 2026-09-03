"""extractor 抽取稳定性：容错解析 + 结构化校验 + 修正重试测试。"""

from research.extractor import _extract_valid, _extract_with_retry, _parse_items
from research.models import ResearchPlan


def _plan():
    return ResearchPlan(report_type="industry", subject="咖啡", market="全国",
                        time_range="近1年", audience="普通读者", queries=[], display="t")


def test_parse_items_handles_markdown_wrap():
    """解析带 ```json 包裹与前后杂文的输出。"""
    raw = '好的，结果如下：\n```json\n[{"claim": "市场规模约100亿", "category": "市场规模", "source_ids": [1]}]\n```\n以上。'
    items = _parse_items(raw)
    assert len(items) == 1
    assert items[0]["claim"] == "市场规模约100亿"


def test_parse_items_bad_returns_empty():
    assert _parse_items("不是JSON") == []
    assert _parse_items("{}") == []


def test_extract_valid():
    ok = [{"claim": "a", "category": "市场规模", "source_ids": [1]},
          {"claim": "b", "category": "增速", "source_ids": [2]},
          {"claim": "c", "category": "趋势", "source_ids": [1, 2]}]
    assert _extract_valid(ok)
    assert not _extract_valid([])
    assert not _extract_valid([{"claim": "a", "category": "x", "source_ids": []}])  # 单条+无来源


def test_extract_with_retry_first_fail_then_ok():
    """首次劣化（无 source_ids）→ 触发修正重试并成功。"""
    calls = []

    def fake_llm(system, user, **kw):
        calls.append(user)
        if len(calls) == 1:
            return '[{"claim": "a", "category": "市场规模", "source_ids": []}]'
        return '[{"claim": "a", "category": "市场规模", "source_ids": [1]},' \
               ' {"claim": "b", "category": "增速", "source_ids": [2]},' \
               ' {"claim": "c", "category": "趋势", "source_ids": [3]}]'

    items = _extract_with_retry(fake_llm, _plan(), [])
    assert len(items) == 3
    assert len(calls) == 2  # 确认重试发生
    assert items[0]["source_ids"] == [1]
