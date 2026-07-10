"""LLM 客户端：支持 OpenAI 兼容协议（OpenAI/DeepSeek/通义千问等）+ Mock 模式。

注意："WorkBuddy 模式"已重命名为"本地预置模式"（preset），因为它实际不调用
WorkBuddy API，而是复用 examples/ 下预先生成的 JSON 报告 —— 真正的生成由
WorkBuddy AI 在对话中完成。

用法：
    from llm import get_provider
    provider = get_provider("openai", timeout=60)  # 或 "mock"
    text = provider.complete(system=..., user=...)
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Protocol


class LLMProvider(Protocol):
    name: str

    def complete(self, system: str, user: str, *, json_mode: bool = True) -> str: ...


# ---------------------------------------------------------------------------
# Mock / 本地预置模式 —— 使用 examples/ 下的预生成 JSON
# ---------------------------------------------------------------------------

class MockProvider:
    """本地预置模式：从 examples/<preset>.json 读取预生成报告。

    用户若想生成新报告，应走 openai 模式或直接在 WorkBuddy 对话中生成。
    """
    name = "mock"

    def __init__(self, preset: str | None = None, timeout: int = 60):
        self.preset = preset or "generic"
        self.timeout = timeout

    def complete(self, system: str, user: str, *, json_mode: bool = True) -> str:
        here = os.path.dirname(os.path.abspath(__file__))
        examples_dir = os.path.join(here, "examples")
        preset_path = os.path.join(examples_dir, f"{self.preset}.json")
        if os.path.exists(preset_path):
            with open(preset_path, "r", encoding="utf-8") as f:
                return f.read()

        # 兜底：generic 占位
        m = re.search(r"主题[：:]\s*\*\*(.+?)\*\*", user)
        subject = m.group(1) if m else "未知主题"
        report = {
            "meta": {
                "title": f"{subject}分析报告（Mock 数据）",
                "subject": subject,
                "type": "industry",
                "generated_at": "2026-07-10T00:00:00+08:00",
            },
            "summary": f"这是一份关于 {subject} 的演示报告（Mock 模式）。\n\n要获得真实数据，请配置 OPENAI_API_KEY 或使用其他 AI 提供商。",
            "sections": [
                {
                    "title": "市场概览",
                    "content": f"**{subject}** 是一个示例主题。实际运行时会调用 LLM 生成完整内容。",
                    "chart": {
                        "type": "bar",
                        "title": f"{subject} 市场规模（示例）",
                        "data": {"categories": ["2021", "2022", "2023", "2024", "2025"],
                                 "values": [100, 130, 165, 210, 270], "unit": "亿元"},
                    },
                },
            ],
            "appendix": {"data_sources": ["Mock 数据"], "limitations": "此为演示数据，不具备分析价值。"},
        }
        return json.dumps(report, ensure_ascii=False)


# WorkBuddyProvider 已重命名为 MockProvider，保留别名做向后兼容
class WorkBuddyProvider(MockProvider):
    """向后兼容别名 —— 实际行为等同于 MockProvider。

    历史说明：原意是在 WorkBuddy 对话中生成报告后通过 CLI 渲染，但实际
    使用时容易与用户输入错配，且增加理解成本。已统一为"本地预置模式"。
    """
    name = "workbuddy"


# ---------------------------------------------------------------------------
# OpenAI 兼容 Provider —— 支持 base_url 自定义 + 超时 + 重试
# ---------------------------------------------------------------------------

class OpenAIProvider:
    name = "openai"

    def __init__(self, timeout: int = 60, max_retries: int = 2):
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "未配置 OPENAI_API_KEY。请设置环境变量，或使用 --ai mock 走演示模式。"
            )
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=max_retries)
        self.model = model
        self.timeout = timeout

    def complete(self, system: str, user: str, *, json_mode: bool = True) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.4,
            "timeout": self.timeout,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# 工厂
# ---------------------------------------------------------------------------

def get_provider(name: str, preset: str | None = None, *,
                 timeout: int = 60, max_retries: int = 2) -> LLMProvider:
    name = (name or "mock").lower()
    if name == "openai":
        return OpenAIProvider(timeout=timeout, max_retries=max_retries)
    if name in ("workbuddy", "mock"):
        # 两个名字都走 MockProvider
        return MockProvider(preset=preset, timeout=timeout)
    raise ValueError(f"未知 AI 提供商: {name}")


def extract_json(text: str) -> dict:
    """从 LLM 输出中尽量稳健地解析 JSON。"""
    text = text.strip()
    # 去 markdown 围栏
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # 直接尝试
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 截取首个 { ... } 块
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError(f"无法从 LLM 输出解析 JSON: {text[:200]}...")
    return json.loads(m.group(0))
