"""DeepSeek LLM client (OpenAI-compatible) via langchain-openai."""
from __future__ import annotations

import os

from langchain_openai import ChatOpenAI


def get_llm(temperature: float = 0.3) -> ChatOpenAI:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set in env")
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=api_key,
        base_url="https://api.deepseek.com",
        temperature=temperature,
        timeout=30,
        max_retries=1,
    )
