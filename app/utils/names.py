import re
from typing import Optional


def normalize_name(value: Optional[str]) -> str:
    if not value:
        return ""
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_client(value: Optional[str]) -> str:
    return normalize_name(value)
