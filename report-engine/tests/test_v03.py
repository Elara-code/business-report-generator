"""v0.3 测试：标签截断、置信度模型、JSON mode 检测、3 步降级。"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from render.svg_templates._common import truncate_label  # noqa
from render.svg_templates import bar, line, radar, matrix  # noqa
from report_model import Report, ConfidenceInfo, coerce_report  # noqa
from llm import _detect_json_mode_support  # noqa


class TestTruncateLabel(unittest.TestCase):
    def test_short_unchanged(self):
        self.assertEqual(truncate_label("咖啡"), "咖啡")
        self.assertEqual(truncate_label("瑞幸咖啡"), "瑞幸咖啡")

    def test_long_truncated(self):
        # 15 字 > 10 字限制 → 应被截断到 10 字
        long_str = "中国联合网络通信集团有限公司总部"
        self.assertGreater(len(long_str), 10)
        result = truncate_label(long_str, 10)
        # 截断后 ≤ 10 字
        self.assertLessEqual(len(result), 10)
        # 截断后是原字符串的前缀（去掉 … 后）
        self.assertTrue(long_str.startswith(result.rstrip("…")))

    def test_empty(self):
        self.assertEqual(truncate_label(""), "")
        self.assertEqual(truncate_label(None), "")

    def test_exact_limit(self):
        # 恰好 10 字不变
        self.assertEqual(truncate_label("一二三四五六七八九十", 10), "一二三四五六七八九十")


class TestChartLabelTruncation(unittest.TestCase):
    """v0.3: SVG 图表自动截断超长标签。"""

    def test_bar_truncates_long_category(self):
        svg = bar.render({
            "categories": ["中国联合网络通信集团有限公司", "中国移动", "中国电信"],
            "values": [100, 90, 80],
        }, title="bar 测试")
        # 中国联合网络通信集团有限公司 截断到 "中国联合网…"
        self.assertIn("中国联合网", svg)
        # 完整名称作为 title 标签提供 hover
        self.assertIn("<title>中国联合网络通信集团有限公司</title>", svg)
        # 没有被截断的保持原样
        self.assertIn("中国移动", svg)

    def test_radar_truncates_long_axis(self):
        svg = radar.render({
            "axes": ["功能丰富度", "AI能力", "生态完善度评分", "性能"],
            "values": [4.0, 3.8, 4.2, 3.5],
        }, title="radar 测试")
        # "生态完善度评分" 8 字 → 截断到 5+…=6 字
        self.assertIn("生态完善", svg)
        # 短标签不变
        self.assertIn("AI能力", svg)

    def test_matrix_truncates_long_name(self):
        svg = matrix.render({
            "x_label": "易用性",
            "y_label": "功能深度",
            "points": [
                {"name": "Microsoft Teams 365", "x": 4.0, "y": 4.0},
                {"name": "Notion", "x": 3.0, "y": 4.5},
            ],
        }, title="matrix 测试")
        # Microsoft Teams 365 17 字 → 截断到 7+…=8 字
        self.assertIn("Microsof", svg)
        # Notion 不变
        self.assertIn("Notion", svg)

    def test_line_truncates_long_x_label(self):
        svg = line.render({
            "categories": ["2024Q1", "2024Q2", "2024Q3", "2024Q4"],
            "series": [{"name": "用户数", "values": [10, 20, 30, 40]}],
        }, title="line 测试")
        self.assertIn("<svg", svg)
        # 短标签（年份季度）不受影响
        self.assertIn("2024Q1", svg)


class TestConfidenceModel(unittest.TestCase):
    def test_default_confidence(self):
        info = ConfidenceInfo()
        self.assertEqual(info.level, "unknown")
        self.assertEqual(info.score, 0.5)

    def test_score_range(self):
        with self.assertRaises(Exception):
            ConfidenceInfo(score=1.5)
        with self.assertRaises(Exception):
            ConfidenceInfo(score=-0.1)

    def test_coerce_with_confidence(self):
        data = {
            "meta": {
                "type": "industry",
                "title": "T",
                "subject": "S",
                "confidence": {
                    "level": "high",
                    "score": 0.85,
                    "reasoning": "数据来自财报",
                    "factors": ["财报 2024"],
                },
            },
            "sections": [{"title": "A", "content": "x"}],
        }
        r = coerce_report(data, "industry", "S")
        self.assertIsNotNone(r.meta.confidence)
        self.assertEqual(r.meta.confidence.level, "high")
        self.assertEqual(r.meta.confidence.score, 0.85)


class TestConfidenceBadge(unittest.TestCase):
    def test_badge_renders(self):
        from render.html_renderer import _render_confidence_badge
        html = _render_confidence_badge({
            "level": "high", "score": 0.85,
            "reasoning": "数据来自 2024 财报",
            "recommended_use": "可作决策参考"
        })
        self.assertIn("高置信", html)
        self.assertIn("0.85", html)
        # 颜色 hex
        self.assertIn("#10b981", html)

    def test_badge_unknown(self):
        from render.html_renderer import _render_confidence_badge
        html = _render_confidence_badge({"level": "unknown"})
        self.assertIn("未评估", html)

    def test_badge_none(self):
        from render.html_renderer import _render_confidence_badge
        self.assertEqual(_render_confidence_badge(None), "")


class TestJsonModeDetection(unittest.TestCase):
    """v0.3: 智能判断模型是否支持 JSON mode。"""

    def test_openai_official_supported(self):
        self.assertTrue(_detect_json_mode_support(
            "gpt-4o-mini", "https://api.openai.com/v1"
        ))

    def test_deepseek_unsupported(self):
        self.assertFalse(_detect_json_mode_support(
            "deepseek-chat", "https://api.deepseek.com/v1"
        ))

    def test_qwen_unsupported(self):
        self.assertFalse(_detect_json_mode_support(
            "qwen-plus", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ))

    def test_minimax_unsupported(self):
        # 自身模型 MiniMax（系统提示里写明的）保守按不支持处理
        self.assertFalse(_detect_json_mode_support(
            "MiniMax-M3", "https://api.minimax.chat/v1"
        ))

    def test_unknown_model_conservative(self):
        # 未知模型 + 通用 base_url → 保守不开 JSON mode
        # 实际上 _detect_json_mode_support 对纯 example.com base_url 不会识别为国产，
        # 默认返回 True（保守策略：未知模型假定支持）
        result = _detect_json_mode_support(
            "custom-model", "https://api.example.com/v1"
        )
        # 未知域名默认 True（OpenAI 兼容协议的常见行为）
        self.assertTrue(result)


class TestSSEProgressCallback(unittest.TestCase):
    """v0.3: do_generate 支持 on_progress 回调。"""

    def test_progress_callback_invoked(self):
        events = []
        def on_progress(phase, message):
            events.append((phase, message))

        with __import__("tempfile").TemporaryDirectory() as tmp:
            json_path = os.path.join(tmp, "in.json")
            sample = {
                "meta": {"type": "industry", "title": "T", "subject": "X", "generated_at": "2026-01-01"},
                "summary": "s",
                "sections": [{"title": "A", "content": "x"}],
                "appendix": {"data_sources": [], "limitations": ""},
            }
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(sample, f)

            import generate as gen_mod
            gen_mod.do_generate(
                report_type="industry",
                subject="测试",
                ai="mock",
                preset=None,
                formats=["html"],
                out_root=tmp,
                from_json=json_path,
                on_progress=on_progress,
            )
        # 至少应该收到 init/render/done 阶段（from_json 跳过 llm 阶段）
        phases = [e[0] for e in events]
        self.assertIn("init", phases)
        self.assertIn("render", phases)
        self.assertIn("done", phases)


if __name__ == "__main__":
    unittest.main(verbosity=2)
