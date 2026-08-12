"""
Name / client / month normalization helpers.

All rules are format-driven (punctuation, order, whitespace) — no person-specific cases.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional


_ROLE_SUFFIX_RE = re.compile(
    r"\s*[-–—,/]\s*(consultant|contractor|employee|resource|worker|temp)\s*$",
    re.I,
)
_MULTI_SPACE_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^\w\s]")


def normalize_name(name: Optional[str]) -> str:
    """
    Normalize a person name for comparison.
    Handles casing, punctuation, whitespace, and "Last, First" ordering.
    """
    if not name:
        return ""

    text = str(name).strip().strip('"').strip("'")
    text = _ROLE_SUFFIX_RE.sub("", text)

    # Last, First [Middle] → First [Middle] Last
    if "," in text:
        left, right = text.split(",", 1)
        left, right = left.strip(), right.strip()
        if left and right:
            text = f"{right} {left}"

    text = text.lower().strip()
    # Keep letters/digits/spaces only (drops periods in initials, commas, etc.)
    text = _NON_ALNUM_RE.sub(" ", text)
    text = _MULTI_SPACE_RE.sub(" ", text).strip()
    return text


def parse_name_tokens(name: Optional[str]) -> Dict[str, object]:
    """
    Split a name into comparable tokens after normalization.

    Returns:
      tokens, first, last, middle, initials (single-char tokens), full tokens list
    """
    normalized = normalize_name(name)
    tokens = [t for t in normalized.split() if t]
    if not tokens:
        return {
            "normalized": "",
            "tokens": [],
            "first": "",
            "last": "",
            "middle": [],
            "initials": [],
        }

    if len(tokens) == 1:
        return {
            "normalized": normalized,
            "tokens": tokens,
            "first": tokens[0],
            "last": tokens[0],
            "middle": [],
            "initials": [tokens[0]] if len(tokens[0]) == 1 else [],
        }

    return {
        "normalized": normalized,
        "tokens": tokens,
        "first": tokens[0],
        "last": tokens[-1],
        "middle": tokens[1:-1],
        "initials": [t for t in tokens if len(t) == 1],
    }


def normalize_email(email: Optional[str]) -> str:
    if not email:
        return ""
    return str(email).lower().strip()


def normalize_phone(phone: Optional[str]) -> str:
    if not phone:
        return ""
    digits = re.sub(r"\D", "", str(phone))
    return digits.ljust(10, "0")[:10]


def normalize_month_year(month_date_str: str) -> str:
    """
    Convert various date formats to YYYY-MM string.

    Input examples: "5/2026", "2026-05", "May 2026", "05/2026"
    Output: "2026-05"
    """
    if not month_date_str:
        return ""

    month_date_str = str(month_date_str).strip()

    if "/" in month_date_str:
        parts = month_date_str.split("/")
        if len(parts) == 2:
            try:
                month = int(parts[0])
                year = int(parts[1])
                return f"{year:04d}-{month:02d}"
            except ValueError:
                pass

    if "-" in month_date_str:
        parts = month_date_str.split("-")
        if len(parts) == 2:
            try:
                year = int(parts[0])
                month = int(parts[1])
                return f"{year:04d}-{month:02d}"
            except ValueError:
                pass

    return month_date_str


def normalize_client_name(client: Optional[str]) -> str:
    """
    Normalize client company name by casing/punctuation and generic legal suffixes.

    Also strips common client-code suffixes such as ``Abbott:4215`` → ``abbott``.
    """
    if not client:
        return ""

    raw = str(client).strip()
    # Client:identifier style (QuickBooks / ERP) — keep the company label only
    if ":" in raw:
        left = raw.split(":", 1)[0].strip()
        if left:
            raw = left

    name = normalize_name(raw)
    # Drop trailing legal-entity tokens dynamically (token-based, not brand-specific)
    legal_tokens = {
        "inc", "incorporated", "ltd", "limited", "llc", "corp",
        "corporation", "co", "company", "plc", "lp", "llp",
    }
    parts = [p for p in name.split() if p not in legal_tokens]
    # Drop pure numeric tokens (often leftover account/site codes)
    parts = [p for p in parts if not p.isdigit()]
    return " ".join(parts).strip()


def token_sort_key(tokens: List[str]) -> str:
    return " ".join(sorted(tokens))
