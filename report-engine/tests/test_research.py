"""研究流水线（v1）单元测试：规划 / 检索 / 抽取 / 验证 / 起草 / 端到端。"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # report-engine 根目录

from research import (  # noqa: E402
    build_plan, run_research, get_searcher,
    draft_report, attach_evidence, extract_facts, verify_facts,
)
from research.models import ResearchPlan  # noqa: E402
from research.planner import _split_competitors  # noqa: E402


class TestPlanner(unittest.TestCase):
    def test_defaults(self):
        p = build_plan("industry", "现制咖啡")
        self.assertEqual(p.market, "全国")
        self.assertEqual(p.time_range, "近1年")
        self.assertEqual(p.audience, "普通读者")
        self.assertTrue(p.queries)

    def test_explicit_values(self):
        p = build_plan("industry", "现制咖啡", market="华东", time_range="近3年", audience="投资者")
        self.assertEqual(p.market, "华东")
        self.assertEqual(p.time_range, "近3年")
        self.assertEqual(p.audience, "投资者")

    def test_competitor_split(self):
        a, b = _split_competitors("Notion vs Obsidian")
        self.assertEqual(a, "Notion")
        self.assertEqual(b, "Obsidian")


class TestSearcher(unittest.TestCase):
    def test_curated(self):
        searcher, warn = get_searcher(prefer="curated")
        self.assertEqual(searcher.name, "curated")
        res = searcher.search("现制咖啡 市场规模 全国", limit=8)
        self.assertGreaterEqual(len(res), 3)

    def test_curated_autofallback(self):
        searcher, _ = get_searcher(prefer="auto")
        self.assertIn(searcher.name, ("ddg", "duckduckgo", "curated"))


class TestExtractMerge(unittest.TestCase):
    def test_merge_duplicate_claim(self):
        plan = build_plan("industry", "现制咖啡")
        searcher, _ = get_searcher(prefer="curated")
        sources = searcher.search(plan.queries[0], limit=12)
        facts = extract_facts(plan, sources, llm=None)
        # 2510 市场规模出现在 3 个来源 → 合并后 evidence 应为 3
        mkt = [f for f in facts if "2510" in f.claim]
        self.assertEqual(len(mkt), 1)
        self.assertEqual(len(set(mkt[0].evidence)), 3)


class TestVerifier(unittest.TestCase):
    def test_conflict_and_status(self):
        plan = build_plan("industry", "现制咖啡")
        searcher, _ = get_searcher(prefer="curated")
        sources = searcher.search(plan.queries[0], limit=12)
        facts = extract_facts(plan, sources, llm=None)
        facts = verify_facts(facts, sources)
        statuses = {f.status for f in facts}
        self.assertIn("verified", statuses)
        self.assertIn("unverified", statuses)
        # 2510 vs 2680 市场规模 → 冲突
        conflicts = [f for f in facts if f.status == "conflicted"]
        self.assertEqual(len(conflicts), 2)

    def test_confidence_computable(self):
        from research.verifier import compute_confidence
        conf = compute_confidence([])
        self.assertEqual(conf["level"], "unknown")
        self.assertGreaterEqual(conf["score"], 0.10)


class TestOfflineAssembly(unittest.TestCase):
    def test_draft_and_evidence(self):
        plan = build_plan("product", "Notion")
        searcher, _ = get_searcher(prefer="curated")
        chain = run_research(plan, searcher, llm=None)
        raw = draft_report(plan, chain, llm=None)
        raw = attach_evidence(raw, chain)
        self.assertIn("summary", raw)
        self.assertIn("sections", raw)
        self.assertIn("evidence", raw)
        self.assertIn("sources", raw["evidence"])
        self.assertIn("facts", raw["evidence"])
        self.assertIn("confidence", raw["meta"])


class TestEndToEnd(unittest.TestCase):
    def _gen(self, rt, subj, preset):
        import generate
        report, outputs, target = generate.do_generate(
            report_type=rt, subject=subj, ai="mock", preset=preset,
            formats=["html", "md"], out_root="/tmp/brg_test_e2e", from_json=None)
        self.assertTrue(os.path.exists(outputs["html"]))
        self.assertTrue(os.path.exists(outputs["md"]))
        self.assertTrue(report.evidence and report.evidence["sources"])
        return report

    def test_industry(self):
        r = self._gen("industry", "中国现制咖啡", "coffee")
        self.assertEqual(r.meta.type, "industry")

    def test_product(self):
        r = self._gen("product", "Notion", "notion")
        self.assertEqual(r.meta.type, "product")

    def test_competitor(self):
        r = self._gen("competitor", "Notion vs Obsidian", "notion-vs-obsidian")
        self.assertEqual(r.meta.type, "competitor")

    def test_from_json_still_works(self):
        import generate
        sample = os.path.join(os.path.dirname(HERE), "examples", "coffee.json")
        if not os.path.exists(sample):
            self.skipTest("examples/coffee.json 不存在")
        report, outputs, _ = generate.do_generate(
            report_type="industry", subject="中国现制咖啡", ai="mock", preset=None,
            formats=["html"], out_root="/tmp/brg_test_e2e", from_json=sample)
        self.assertTrue(os.path.exists(outputs["html"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
