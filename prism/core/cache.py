"""Cache helpers stub."""

from typing import Any, Optional

_CACHE: dict[str, Any] = {}


def get_cache(key: str) -> Optional[Any]:
    return _CACHE.get(key)


def set_cache(key: str, value: Any) -> None:
    _CACHE[key] = value


def clear_cache() -> None:
    _CACHE.clear()
