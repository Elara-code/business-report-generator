"""单元测试：chart 数据规范化层（LLM 输出形态 → 模板字段 / 文字卡降级）。"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from render.svg_templates import render_chart  # noqa


class TestChartNormalize(unittest.TestCase):
    """LLM 不守 schema 时也要能渲染出合理内容，绝不出现崩溃/裸占位。"""

    def test_value_chain_string_stages(self):
        """字符串 stages 列表：不崩，渲染出节点链。"""
        svg = render_chart("value_chain", {"stages": ["底座", "中间件", "应用"]}, "价值链")
        self.assertIn("<svg", svg)
        self.assertIn("底座", svg)
        self.assertNotIn("图表渲染失败", svg)

    def test_bar_items_labels(self):
        """items:[{label,value}] → 柱状图。"""
        svg = render_chart("bar", {"items": [{"label": "A", "value": 968.3},
                                             {"label": "B", "value": 6.3}],
                                    "note": "来源[1]"}, "IDC")
        self.assertIn("<svg", svg)
        self.assertIn("A", svg)
        self.assertIn("B", svg)

    def test_bar_labels_values(self):
        svg = render_chart("bar", {"labels": ["甲", "乙"], "values": [10, 20], "unit": "%"})
        self.assertIn("<svg", svg)

    def test_line_text_only_fallback(self):
        """line 只有文字方向、无数值 → 文字卡（而非裸占位）。"""
        out = render_chart("line", {"labels": ["期初", "期末"], "方向": "用户规模快速增长"})
        self.assertNotIn("<svg", out)
        self.assertIn("用户规模快速增长", out)
        self.assertNotIn("数据缺失", out)

    def test_matrix_scenarios_fallback(self):
        """matrix 只有文字场景、无点位 → 文字卡。"""
        out = render_chart("matrix", {"axis_x": "X", "axis_y": "Y",
                                      "scenarios": ["冲击者视角", "基础设施视角"]})
        self.assertNotIn("<svg", out)
        self.assertIn("冲击者视角", out)
        self.assertNotIn("无点位", out)

    def test_radar_dimensions_fallback(self):
        """radar 只有维度、无打分 → 文字卡。"""
        out = render_chart("radar", {"dimensions": ["成本", "效率"], "说明": "定性"})
        self.assertNotIn("<svg", out)
        self.assertIn("成本", out)
        self.assertNotIn("轴缺失", out)

    def test_canvas_single_key_fallback(self):
        """canvas 只有一个方向、不满 3 格 → 文字卡（避免大片空白）。"""
        out = render_chart("canvas", {"技能方向": ["行业分析", "市场调查"]})
        self.assertNotIn("<svg", out)
        self.assertIn("行业分析", out)

    def test_canvas_full_renders(self):
        """canvas 完整 9 格 → SVG。"""
        data = {k: ["a", "b"] for k in
                ("key_partners", "key_activities", "value_propositions",
                 "customer_relationships", "customer_segments", "key_resources",
                 "channels", "cost_structure", "revenue_streams")}
        svg = render_chart("canvas", data, "画布")
        self.assertIn("<svg", svg)

    def test_data_is_string_no_crash(self):
        """data 是字符串（LLM 最乱的输出）→ 不崩，返回空或文字卡。"""
        out = render_chart("bar", "没有任何结构", "标题")
        self.assertNotIn("图表渲染失败", out)
        self.assertNotIn("AttributeError", out)

    def test_unknown_type(self):
        out = render_chart("whatever", {"a": 1})
        self.assertIn("未知图表类型", out)

    def test_null_type(self):
        self.assertEqual(render_chart("null", {}), "")


if __name__ == "__main__":
    unittest.main()
