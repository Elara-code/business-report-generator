"""报告数据结构的常量与类型提示（运行时仅做字符串常量参考）。"""
from __future__ import annotations

SUPPORTED_TYPES = ("industry", "product", "competitor")
SUPPORTED_FORMATS = ("html", "md", "pdf")
SUPPORTED_AI = ("workbuddy", "openai", "mock")

# 报告类型 → 章节清单（用于 prompt 与渲染时的兜底顺序）
REPORT_SECTIONS: dict[str, list[str]] = {
    "industry": [
        "执行摘要",
        "市场概览",
        "价值链分析",
        "商业模式画布",
        "竞争格局",
        "关键玩家",
        "趋势与机会",
        "风险与建议",
    ],
    "product": [
        "执行摘要",
        "产品定位",
        "目标用户",
        "核心功能拆解",
        "用户旅程",
        "商业模式",
        "增长策略",
        "优势与启示",
    ],
    "competitor": [
        "执行摘要",
        "产品速览",
        "定位对比",
        "功能矩阵",
        "商业模式对比",
        "用户体验对比",
        "增长策略对比",
        "SWOT 矩阵",
        "战略总结",
    ],
}

# 行业报告 prompt 的系统角色
SYSTEM_PROMPT = """你是一位资深商业分析师，擅长为投资人和创业者撰写结构化、可视化的商业分析报告。
你的输出必须是严格合法的 JSON，不要包含 ```json 或任何额外文字。"""

# 强制要求 LLM 返回的 JSON 顶层 schema（描述性，渲染时再做容错）
JSON_SCHEMA_HINT = """
{
  "meta": {
    "title": "报告标题（中文）",
    "subject": "用户输入的主题",
    "type": "industry | product | competitor",
    "generated_at": "ISO8601 字符串"
  },
  "summary": "150-250 字执行摘要（中文，结论先行）",
  "sections": [
    {
      "title": "章节标题",
      "content": "章节正文（中文，Markdown 语法可用 **粗体**、- 列表、> 引用、表格）",
      "chart": {
        "type": "bar | line | radar | canvas | funnel | value_chain | matrix | null",
        "title": "图表标题（如果不需要图表则填 null）",
        "data": { /* 与 type 对应的数据，详见 prompt 内说明 */ }
      }
    }
  ],
  "appendix": {
    "data_sources": ["来源 1", "来源 2"],
    "limitations": "数据局限性说明（一段话）"
  }
}
"""
