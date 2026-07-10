"""LLM 客户端：支持 OpenAI 兼容协议（OpenAI/DeepSeek/通义千问等）+ Mock 模式。

用法：
    from llm import get_provider
    provider = get_provider("openai")  # 或 "workbuddy" / "mock"
    text = provider.complete(system=..., user=...)
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Protocol


class LLMProvider(Protocol):
    name: str

    def complete(self, system: str, user: str, *, json_mode: bool = True) -> str: ...


# ---------------------------------------------------------------------------
# Mock Provider —— 用于无 API Key 的演示 / 单测 / 跑通流程
# ---------------------------------------------------------------------------

class MockProvider:
    name = "mock"

    def __init__(self, preset: str | None = None):
        # preset 决定返回哪份预生成报告（coffee / notion / notion-vs-obsidian / generic）
        self.preset = preset or "generic"

    def complete(self, system: str, user: str, *, json_mode: bool = True) -> str:
        # 优先用 preset 文件（已生成的 JSON），跳过 prompt 模板
        here = os.path.dirname(os.path.abspath(__file__))
        examples_dir = os.path.join(here, "examples")
        preset_path = os.path.join(examples_dir, f"{self.preset}.json")
        if os.path.exists(preset_path):
            with open(preset_path, "r", encoding="utf-8") as f:
                return f.read()

        # 否则从 user 里抽主题，生成一个最小可用报告
        m = re.search(r"主题[：:]\s*\*\*(.+?)\*\*", user)
        subject = m.group(1) if m else "未知主题"

        # 否则生成一个最小可用报告
        report = {
            "meta": {
                "title": f"{subject}分析报告（Mock 数据）",
                "subject": subject,
                "type": "industry",
                "generated_at": "2026-07-10T00:00:00+08:00",
            },
            "summary": f"这是一份关于 {subject} 的演示报告（Mock 模式）。\n\n要获得真实数据，请配置 OPENAI_API_KEY 或在 WorkBuddy 对话中让 AI 直接生成。",
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
                {
                    "title": "竞争格局",
                    "content": "示例章节内容。",
                    "chart": {
                        "type": "radar",
                        "title": "波特五力评分",
                        "data": {"axes": ["供应商", "购买者", "新进入", "替代品", "现有竞争"],
                                 "values": [3.5, 4.0, 2.5, 3.0, 4.5]},
                    },
                },
            ],
            "appendix": {
                "data_sources": ["Mock 数据"],
                "limitations": "此为演示数据，不具备分析价值。",
            },
        }
        return json.dumps(report, ensure_ascii=False)


# ---------------------------------------------------------------------------
# OpenAI 兼容 Provider —— 支持 base_url 自定义
# ---------------------------------------------------------------------------

class OpenAIProvider:
    name = "openai"

    def __init__(self):
        # 延迟 import：mock 模式下不依赖 openai
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "未配置 OPENAI_API_KEY。请设置环境变量，或使用 --ai mock 走演示模式。"
            )
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def complete(self, system: str, user: str, *, json_mode: bool = True) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.4,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# WorkBuddy Provider —— 走"对话式"调用（用户在 WorkBuddy 对话里直接说）
# ---------------------------------------------------------------------------

class WorkBuddyProvider:
    """WorkBuddy 模式下，CLI 会读取 examples/ 下用户已准备好的 JSON。

    这是一个**占位实现**：当用户在 WorkBuddy 对话中跟 AI 说"用咖啡行业生成一份"，
    AI 直接在对话中产出 JSON 并保存到 examples/，然后 CLI 用 --ai workbuddy 跑
    渲染流程。这样避免了双重 API 计费。
    """
    name = "workbuddy"

    def __init__(self, preset: str | None = None):
        self.preset = preset or "coffee"
        self._delegate = MockProvider(preset=self.preset)

    def complete(self, system: str, user: str, *, json_mode: bool = True) -> str:
        # 实际生成由 WorkBuddy AI 在对话中完成，CLI 仅复用 examples JSON
        return self._delegate.complete(system, user, json_mode=json_mode)


# ---------------------------------------------------------------------------
# 工厂
# ---------------------------------------------------------------------------

def get_provider(name: str, preset: str | None = None) -> LLMProvider:
    name = (name or "mock").lower()
    if name == "openai":
        return OpenAIProvider()
    if name == "workbuddy":
        return WorkBuddyProvider(preset=preset)
    if name == "mock":
        return MockProvider(preset=preset)
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
