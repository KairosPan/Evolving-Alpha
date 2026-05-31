from __future__ import annotations

import os
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """最小 LLM 接口:给系统/用户提示,返回文本(期望是 JSON 字符串)。"""
    def complete(self, system: str, user: str) -> str: ...


class MockLLMClient:
    """离线测试用:返回脚本化响应,并记录每次 (system, user) 调用。"""

    def __init__(self, scripted: "str | list[str]") -> None:
        self._responses: list[str] = [scripted] if isinstance(scripted, str) else list(scripted)
        if not self._responses:
            raise ValueError("scripted 不能为空")
        self._i = 0
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        r = self._responses[min(self._i, len(self._responses) - 1)]
        self._i += 1
        return r


class DeepSeekClient:
    """DeepSeek(OpenAI 兼容)。lazy import openai;实盘/smoke 用,测试不触达。"""

    def __init__(self, model: str = "deepseek-chat", api_key: str | None = None,
                 base_url: str = "https://api.deepseek.com", temperature: float = 0.3) -> None:
        from openai import OpenAI  # lazy
        key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise RuntimeError("缺少 DEEPSEEK_API_KEY")
        self._client = OpenAI(api_key=key, base_url=base_url)
        self._model = model
        self._temperature = temperature

    def complete(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=self._temperature,
        )
        return resp.choices[0].message.content or ""
