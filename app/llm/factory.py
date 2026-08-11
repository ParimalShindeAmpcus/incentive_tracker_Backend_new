"""Pick LLM provider from config (stub)."""

from app.llm.provider import LLMProvider


def get_provider() -> LLMProvider:
    raise NotImplementedError("No LLM provider configured yet")
