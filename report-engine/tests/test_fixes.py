"""单元测试：funnel 渲染、JSON 校验、preset 错配、from-json 流程、历史报告路径过滤。"""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import schemas  # noqa
from render.svg_templates import funnel, bar, line, radar, canvas, matrix, value_chain  # noqa
from report_model import Report, coerce_report  # noqa
import generate as gen_mod  # noqa


class TestFunnelBug(unittest.TestCase):
    """P0: 修复前 f'{esc(v):,}' 会爆 ValueError（字符串不能 :, 格式化）。"""

    def test_funnel_renders_string_values(self):
        data = {
            "stages": [
                {"name": "访问", "value": 12000000},
                {"name": "注册", "value": 3500000},
                {"name": "付费", "value": 180000},
            ]
        }
        svg = funnel.render(data, title="漏斗测试")
        # 不应该抛异常
        self.assertIn("<svg", svg)
        self.assertIn("访问", svg)
        # 数字应该有千分位
        self.assertIn("12,000,000", svg)
        # 不应该出现 ValueError 字样
        self.assertNotIn("ValueError", svg)

    def test_funnel_handles_zero(self):
        data = {"stages": [{"name": "A", "value": 0}, {"name": "B", "value": 0}]}
        svg = funnel.render(data)
        self.assertIn("<svg", svg)

    def test_funnel_empty(self):
        svg = funnel.render({"stages": []})
        self.assertIn("数据缺失", svg)


class TestOtherCharts(unittest.TestCase):
    """所有 SVG 模板都不应该崩。"""

    def test_bar(self):
        svg = bar.render(
            {"categories": ["A", "B", "C"], "values": [10, 20, 30], "unit": " 亿"},
            title="测试 bar"
        )
        self.assertIn("<svg", svg)
        self.assertIn("A", svg)

    def test_line(self):
        svg = line.render(
            {"categories": ["2020", "2021", "2022"], "series": [{"name": "X", "values": [1, 2, 3]}]},
            title="测试 line"
        )
        self.assertIn("<svg", svg)

    def test_radar_single_series(self):
        svg = radar.render(
            {"axes": ["a", "b", "c"], "values": [1, 2, 3]},
            title="测试 radar"
        )
        self.assertIn("<svg", svg)

    def test_radar_multi_series(self):
        svg = radar.render(
            {"axes": ["a", "b", "c"],
             "series": [{"name": "X", "values": [1, 2, 3]}, {"name": "Y", "values": [3, 2, 1]}]},
            title="测试 radar"
        )
        self.assertIn("<svg", svg)

    def test_canvas(self):
        svg = canvas.render({
            "key_partners": ["A", "B"],
            "key_activities": ["C"],
            "value_propositions": ["D"],
            "customer_relationships": ["E"],
            "customer_segments": ["F"],
            "key_resources": ["G"],
            "channels": ["H"],
            "cost_structure": ["I"],
            "revenue_streams": ["J"],
        }, title="测试 canvas")
        self.assertIn("<svg", svg)

    def test_value_chain(self):
        svg = value_chain.render({"stages": [
            {"name": "上游", "items": ["a", "b"], "margin": "高"},
            {"name": "下游", "items": ["c"], "margin": "中"},
        ]}, title="测试 vc")
        self.assertIn("<svg", svg)

    def test_matrix(self):
        svg = matrix.render({
            "x_label": "X",
            "y_label": "Y",
            "points": [{"name": "P1", "x": 1.0, "y": 2.0}],
        }, title="测试 matrix")
        self.assertIn("<svg", svg)


class TestSchemaValidation(unittest.TestCase):
    """P0: Pydantic 强校验。"""

    def test_minimal_valid(self):
        r = Report.model_validate({
            "meta": {"title": "T", "subject": "S", "type": "industry", "generated_at": "2026-01-01"},
            "summary": "...",
            "sections": [{"title": "A", "content": "x"}],
            "appendix": {"data_sources": [], "limitations": ""},
        })
        self.assertEqual(r.meta.type, "industry")
        self.assertEqual(len(r.sections), 1)

    def test_missing_sections_raises(self):
        with self.assertRaises(Exception):
            Report.model_validate({"sections": []})

    def test_invalid_type_raises(self):
        with self.assertRaises(Exception):
            Report.model_validate({
                "meta": {"type": "unknown", "title": "T"},
                "sections": [{"title": "A"}],
            })

    def test_extra_fields_kept(self):
        """LLM 经常带额外字段，应宽松处理。"""
        r = Report.model_validate({
            "meta": {"type": "industry"},
            "sections": [{"title": "A", "extra_field": "kept"}],
            "extra_top": "kept too",
        })
        self.assertIn("extra_field", r.sections[0].model_extra)


class TestPresetOverride(unittest.TestCase):
    """P0: mock preset 错配时，必须强制覆盖 type/subject。"""

    def test_coffee_preset_with_user_subject_notion(self):
        # 模拟 coffee preset（type=industry, subject=咖啡）
        # 用户输入 "Notion" + type=product
        data = {
            "meta": {"type": "industry", "subject": "中国现制咖啡", "title": "咖啡报告"},
            "summary": "...",
            "sections": [{"title": "市场", "content": "x"}],
        }
        coerced = coerce_report(data, report_type="product", subject="Notion")
        # 必须被强制覆盖
        self.assertEqual(coerced.meta.type, "product")
        self.assertEqual(coerced.meta.subject, "Notion")
        # title 在 preset 里已存在，保留
        self.assertIn("咖啡", coerced.meta.title)


class TestFromJsonFlow(unittest.TestCase):
    """P0: --from-json 流程能跑通。"""

    def test_from_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path = os.path.join(tmp, "in.json")
            sample = {
                "meta": {"type": "industry", "subject": "X", "title": "X报告", "generated_at": "2026-01-01"},
                "summary": "s",
                "sections": [{"title": "A", "content": "x"}],
                "appendix": {"data_sources": [], "limitations": ""},
            }
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(sample, f)

            # 直接调用 do_generate
            report, outputs, target = gen_mod.do_generate(
                report_type="industry",
                subject="新主题",  # 用户覆盖 subject
                ai="mock",
                preset=None,
                formats=["html", "md"],
                out_root=tmp,
                from_json=json_path,
            )
            self.assertTrue(os.path.exists(os.path.join(target, "report.html")))
            self.assertTrue(os.path.exists(os.path.join(target, "report.md")))
            # 报告的 subject 应该是用户输入的，不是 JSON 里的 X
            self.assertEqual(report.meta.subject, "新主题")


class TestUniqueOutDir(unittest.TestCase):
    """P1: 同秒生成多个报告不应冲突。"""

    def test_unique_paths(self):
        paths = set()
        for _ in range(5):
            d = gen_mod.make_out_dir("/tmp", "industry", "咖啡")
            paths.add(d)
        self.assertEqual(len(paths), 5)


class TestSanitization(unittest.TestCase):
    """P1: HTML 渲染器应清洗 LLM 输出中的危险标签。"""

    def test_strips_script(self):
        from render.html_renderer import _md
        result = _md("hello <script>alert('xss')</script> world")
        # <script> 标签必须被剥除
        self.assertNotIn("<script", result)
        # 残余的 alert 文本无害（不是 HTML），但 <script> 标签已消失
        self.assertIn("hello", result)
        self.assertIn("world", result)
        # 关键是没有 <script> 这种可执行标签
        self.assertNotIn("</script>", result)

    def test_strips_event_handler(self):
        from render.html_renderer import _md
        result = _md('<a href="javascript:alert(1)">click</a>')
        # javascript: 协议必须被剥除
        self.assertNotIn("javascript:", result)

    def test_keeps_safe_tags(self):
        from render.html_renderer import _md
        result = _md("**bold** and `code` and a [link](https://example.com)")
        self.assertIn("<strong>", result)
        self.assertIn("<code>", result)
        self.assertIn('href="https://example.com"', result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
