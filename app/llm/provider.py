"""Abstract LLM provider interface (stub)."""

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str, **kwargs: Any) -> str:
        raise NotImplementedError
