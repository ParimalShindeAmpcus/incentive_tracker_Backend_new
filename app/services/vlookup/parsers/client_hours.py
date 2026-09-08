"""
Client hours parsers for Smart Match.

Primary format: Nashik Consolidated File. Column *names* may vary; fields mean:

  Candidate Name → Candidate Name / Name
  Old Hours      → Old Hours / Actual Quantity (Qty)
  New Hours      → New Hours / 160 Hours
  Organisation   → Organisation / Source

The file is already specific to one month (no Month column). Hours Worked
after Smart Match is taken from New Hours.
"""
from __future__ import annotations

import re
from collections import defaultdict
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.services.vlookup.normalization import (
    extract_person_name,
    normalize_client_name,
    normalize_month_year,
    normalize_name,
)


WEEK_ENDING_PATTERNS = [
    re.compile(r"^(?P<name>.+?)\s+FOR THE WEEK ENDING OF\s*[:-]?\s*(?P<date>[\d/\-]+)", re.I),
    re.compile(r"^(?P<name>.+?)\s+FOR THE WEEK ENDING OF\s*[:-]?", re.I),
    re.compile(r"^(?P<name>.+?)\s+FOR THE MONTH OF\s+(?P<month>[A-Za-z]{3,9})", re.I),
    re.compile(r"^(?P<name>.+?)\s+FOR THE PERIOD\s*[:-]?\s*(?P<period>.+)$", re.I),
    re.compile(r"^(?P<name>.+?)\s+FOR THE PERIOD\s*/?\s*BY\s*[:-]?\s*(?P<period>.+)$", re.I),
]


# Canonical field → supported header keys after _normalize_column_name().
# First match in each list wins when more than one variant is present.
CANDIDATE_NAME_ALIASES = [
    "candidate_name",
    "name",
    "employee_name",
    "consultant_name",
    "resource_name",
    "worker_name",
    "full_name",
]
OLD_HOURS_ALIASES = [
    "old_hours",
    "old_hour",
    "actual_quantity_qty",
    "actual_quantity",
    "actual_qty",
]
NEW_HOURS_ALIASES = [
    "new_hours",
    "new_hour",
    "160_hours",
    "160hours",
]
ORGANISATION_ALIASES = [
    "organisation",
    "organization",
    "source",
    "org",
    "vendor",
    "company",
]


def _normalize_column_name(name: Any) -> str:
    """Lowercase, replace punctuation/spaces with underscores (Actual Quantity (Qty) → actual_quantity_qty)."""
    text = str(name).lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _normalized_columns(df: pd.DataFrame) -> List[str]:
    return [_normalize_column_name(c) for c in df.columns]


def _has_any_alias(cols: Any, aliases: List[str]) -> bool:
    keys = {_normalize_column_name(c) for c in cols}
    return bool(keys & set(aliases))


def looks_like_consolidated_hours(df: pd.DataFrame) -> bool:
    """True when the sheet has a name column plus Old Hours and/or New Hours (any supported header)."""
    cols = _normalized_columns(df)
    has_name = _has_any_alias(cols, CANDIDATE_NAME_ALIASES)
    if not has_name:
        has_name = any("candidate" in c and "name" in c for c in cols)
    has_hours = _has_any_alias(cols, NEW_HOURS_ALIASES) or _has_any_alias(cols, OLD_HOURS_ALIASES)
    if not has_hours:
        has_hours = any(("new" in c and "hour" in c) or ("old" in c and "hour" in c) for c in cols)
    return bool(has_name and has_hours)


def parse_client_hours_file(
    file_content: bytes,
    filename: str,
    target_month: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Parse the Nashik Consolidated File used as the second Smart Match file.

    Expected columns (any supported header variant):
      Candidate Name or Name;
      Old Hours or Actual Quantity (Qty);
      New Hours or 160 Hours;
      Organisation or Source.
    There is no Month column — the file is already specific to one month.

    Returns:
        {
          format: str,
          rows: [{candidate_name, organisation, hours_worked, old_hours, ...}],
          candidate_count: int,
          months_found: [],
          warnings: [str]
        }
    """
    _ = target_month
    lower = filename.lower()
    if lower.endswith(".csv"):
        df = _read_csv_bytes(file_content)
    elif lower.endswith((".xlsx", ".xls")):
        df = pd.read_excel(BytesIO(file_content))
    else:
        raise ValueError(f"Unsupported file format: {filename}")

    if df is None or df.empty:
        raise ValueError("Empty uploaded file. The Consolidated File has no data rows.")

    if not looks_like_consolidated_hours(df):
        found = list(df.columns)
        raise ValueError(
            "Smart Match requires a Consolidated File with Candidate Name (or Name), "
            "Old Hours (or Actual Quantity (Qty)), New Hours (or 160 Hours), "
            "and Organisation (or Source). "
            f"Found: {found}"
        )
    return _parse_consolidated_hours(df)


def _parse_consolidated_hours(df: pd.DataFrame) -> Dict[str, Any]:
    warnings: List[str] = []
    rows: List[Dict[str, Any]] = []

    work = df.copy()
    work.columns = _normalized_columns(work)

    name_col = _find_col(work.columns, CANDIDATE_NAME_ALIASES)
    if not name_col:
        for c in work.columns:
            if "name" in c and "org" not in c and "client" not in c and "organisation" not in c:
                name_col = c
                break
    if not name_col:
        raise ValueError(
            "Could not find Candidate Name (or Name) in the Consolidated File. "
            f"Found columns: {list(work.columns)}"
        )

    old_hours_col = _find_col(work.columns, OLD_HOURS_ALIASES)
    new_hours_col = _find_col(work.columns, NEW_HOURS_ALIASES)
    if not new_hours_col:
        for c in work.columns:
            if "new" in c and "hour" in c:
                new_hours_col = c
                break
    if not new_hours_col:
        new_hours_col = _find_col(work.columns, ["hours_worked", "hours", "total_hours"])
    if not new_hours_col:
        for c in work.columns:
            if "hour" in c and c != old_hours_col:
                new_hours_col = c
                break
    if not new_hours_col and old_hours_col:
        new_hours_col = old_hours_col
        warnings.append(
            "New Hours / 160 Hours column was not found; "
            "Old Hours (Actual Quantity) was used for Smart Match hours."
        )
    if not new_hours_col:
        raise ValueError(
            "Could not find New Hours (or 160 Hours) in the Consolidated File. "
            f"Found columns: {list(work.columns)}"
        )

    org_col = _find_col(work.columns, ORGANISATION_ALIASES)

    skipped_blank = 0
    for idx, row in work.iterrows():
        candidate_name = _clean_candidate_name(str(row.get(name_col, "")))
        if not candidate_name or candidate_name.lower() in ("nan", "none"):
            skipped_blank += 1
            continue

        new_hours = _to_float(row.get(new_hours_col))
        old_hours = _to_float(row.get(old_hours_col)) if old_hours_col else None
        if new_hours is None:
            new_hours = old_hours
        if new_hours is None:
            skipped_blank += 1
            continue

        organisation = ""
        if org_col:
            organisation = str(row.get(org_col, "") or "").strip()
            if organisation.lower() in ("nan", "none"):
                organisation = ""

        rows.append(
            {
                "candidate_name": candidate_name,
                "candidate_id": None,
                "client_name": "",
                "organisation": organisation,
                "hours_worked": new_hours,
                "old_hours": old_hours,
                "week": "New Hours",
                "month": "",
                "source_ref": f"row-{idx}",
                "normalized_name": normalize_name(candidate_name),
                "normalized_client": "",
            }
        )

    if skipped_blank:
        warnings.append(
            f"{skipped_blank} Consolidated File row(s) skipped (blank name or hours)."
        )
    if not rows:
        warnings.append(
            f"No hours rows parsed from the Consolidated File. Columns: {list(work.columns)}"
        )

    result = _finalize_result("consolidated", rows, warnings, "")
    result["months_found"] = []
    result["candidate_count"] = len({r["candidate_name"] for r in rows})
    return result


def _decode_bytes(content: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _read_csv_bytes(content: bytes) -> pd.DataFrame:
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"):
        try:
            return pd.read_csv(BytesIO(content), encoding=enc)
        except Exception:
            continue
    return pd.read_csv(BytesIO(content), encoding="utf-8", encoding_errors="replace")


def _finalize_result(
    fmt: str,
    rows: List[Dict[str, Any]],
    warnings: List[str],
    target: str,
) -> Dict[str, Any]:
    months = sorted({r["month"] for r in rows if r.get("month")})
    names = {r["candidate_name"] for r in rows}
    return {
        "format": fmt,
        "rows": rows,
        "candidate_count": len(names),
        "months_found": months,
        "target_month": target or None,
        "warnings": warnings,
        "row_count": len(rows),
    }


def _extract_name_from_memo(memo: str) -> str:
    if not memo:
        return ""
    text = memo.strip().strip('"')
    for pattern in WEEK_ENDING_PATTERNS:
        m = pattern.match(text)
        if m:
            return _clean_candidate_name(m.group("name"))
    extracted = extract_person_name(text)
    if extracted:
        return _clean_candidate_name(extracted)
    return _clean_candidate_name(text)


def _clean_candidate_name(name: str) -> str:
    if not name:
        return ""
    text = str(name).strip().strip('"').strip("'")
    text = extract_person_name(text) or text
    text = re.sub(r"\s+", " ", text)
    # Drop trailing punctuation / consultant suffixes
    text = re.sub(
        r"\s*[-–—]\s*(consultant|contractor|employee|resource)\s*$",
        "",
        text,
        flags=re.I,
    )
    text = text.strip(" -,:;")
    # Reject if mostly digits / codes
    if re.fullmatch(r"[\d\W_]+", text or ""):
        return ""
    return text


def _to_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)) and not pd.isna(val):
        return float(val)
    text = str(val).strip().replace(",", "")
    if not text or text.lower() in ("nan", "none", ""):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _find_col(columns, candidates: List[str]) -> Optional[str]:
    cols = list(columns)
    for c in candidates:
        if c in cols:
            return c
    return None


def invoice_letter_prefix(source_ref: Optional[str]) -> str:
    """
    Extract a generic invoice letter prefix such as GANT from ``GANT-06/07``.

    Format-driven only — never person-specific. Used as a weak corroborating
    signal against first/last name starts when those names already match.
    """
    if not source_ref:
        return ""
    text = str(source_ref).strip().upper()
    if not text or text.lower().startswith("line-") or text.lower().startswith("row-"):
        return ""
    match = re.match(r"^([A-Z]{2,8})", text)
    return match.group(1) if match else ""


def aggregate_hours_by_candidate(
    rows: List[Dict[str, Any]],
    all_rows_for_cumulative: Optional[List[Dict[str, Any]]] = None,
    *,
    group_by_month: bool = True,
) -> List[Dict[str, Any]]:
    """
    Collapse parsed invoice/week rows into groups used by the matcher.

    When group_by_month is True (legacy), one group per candidate+month.
    When False, one group per candidate identity (name + client) across all
    months so VLOOKUP can match once and filter hours later.

    Template Hours start at 0; these aggregated hours are what get written
    into the Hours Template after matching.

    For mid-month joiners, a single month may be < 160h. When all_rows_for_cumulative
    is provided (full multi-month client extract), also attach cumulative_hours
    across months so Accounts can see progress toward 160h.
    """
    groups: Dict[Tuple[str, ...], Dict[str, Any]] = {}

    for row in rows:
        name = row["candidate_name"]
        month = row.get("month") or ""
        client = row.get("client_name") or ""
        organisation = str(row.get("organisation") or "").strip()
        if group_by_month:
            key: Tuple[str, ...] = (normalize_name(name), month)
        else:
            # Organisation is vendor (Ampcus/Bravens/ITech), not Hours Template client.
            # Keep identities unique without feeding org into client-name scoring.
            key = (normalize_name(name), normalize_client_name(organisation or client))
        if key not in groups:
            groups[key] = {
                "candidate_name": name,
                "candidate_id": row.get("candidate_id"),
                "client_name": client,
                "organisation": organisation,
                "month": month if group_by_month else "",
                "total_hours": 0.0,
                "cumulative_hours": 0.0,
                "monthly_hours": {},
                "weekly_breakdown": defaultdict(float),
                "weekly_by_month": {},
                "source_rows": [],
                "client_votes": defaultdict(float),
                "name_votes": defaultdict(float),
                "invoice_prefixes": set(),
            }
        g = groups[key]
        hours = float(row.get("hours_worked") or 0)
        g["total_hours"] += hours
        week = row.get("week") or "Week"
        g["weekly_breakdown"][week] += hours
        g["source_rows"].append(row)
        if g.get("old_hours") is None and row.get("old_hours") is not None:
            try:
                g["old_hours"] = float(row.get("old_hours"))
            except (TypeError, ValueError):
                pass
        if client:
            g["client_votes"][client] += hours
        g["name_votes"][name] += hours
        prefix = invoice_letter_prefix(str(row.get("source_ref") or ""))
        if prefix:
            g["invoice_prefixes"].add(prefix)

    # Cumulative hours + per-month weekly breakdown across the full client file
    cumulative_source = all_rows_for_cumulative if all_rows_for_cumulative is not None else rows
    cumulative_by_name: Dict[str, float] = defaultdict(float)
    monthly_by_name: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    weekly_by_name_month: Dict[str, Dict[str, Dict[str, float]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(float))
    )
    for row in cumulative_source:
        nkey = normalize_name(row["candidate_name"])
        hrs = float(row.get("hours_worked") or 0)
        cumulative_by_name[nkey] += hrs
        m = normalize_month_year(str(row.get("month") or "")) or ""
        if m:
            monthly_by_name[nkey][m] += hrs
            week = row.get("week") or "Week"
            weekly_by_name_month[nkey][m][week] += hrs

    result = []
    for g in groups.values():
        if g["client_votes"]:
            g["client_name"] = max(g["client_votes"].items(), key=lambda x: x[1])[0]
        if g["name_votes"]:
            # Prefer longest name among votes (more complete)
            g["candidate_name"] = max(g["name_votes"].keys(), key=lambda n: (g["name_votes"][n], len(n)))
        nkey = normalize_name(g["candidate_name"])
        g["cumulative_hours"] = round(float(cumulative_by_name.get(nkey, g["total_hours"])), 2)
        g["monthly_hours"] = {
            m: round(h, 2) for m, h in sorted(monthly_by_name.get(nkey, {}).items())
        }
        g["weekly_breakdown"] = {
            week: round(h, 2) for week, h in dict(g["weekly_breakdown"]).items()
        }
        # Full multi-month weekly map so UI can switch months
        g["weekly_by_month"] = {
            m: {week: round(h, 2) for week, h in weeks.items()}
            for m, weeks in sorted(weekly_by_name_month.get(nkey, {}).items())
        }
        g["hours_note"] = _hours_progress_note(g["total_hours"], g["cumulative_hours"])
        prefixes = g.get("invoice_prefixes") or set()
        g["invoice_prefixes"] = sorted(prefixes) if isinstance(prefixes, set) else list(prefixes or [])
        if not group_by_month:
            # Identity match is month-independent; hours are selected later.
            months_present = [
                m for m in (g.get("monthly_hours") or {}) if normalize_month_year(str(m or ""))
            ]
            g["month"] = months_present[-1] if months_present else ""
        del g["client_votes"]
        del g["name_votes"]
        result.append(g)
    return result


def _hours_progress_note(
    month_hours: float,
    cumulative_hours: float,
    cap: float = None,
) -> str:
    """Explain partial-month / multi-month progress using configurable cap."""
    from app.config import get_settings

    threshold = float(cap if cap is not None else getattr(get_settings(), "HOURS_VALIDATION_CAP", getattr(get_settings(), "hours_validation_cap", 160.0)))
    if month_hours >= threshold:
        return f"Monthly hours meet/exceed configured cap ({threshold:.0f}h)"
    if cumulative_hours >= threshold:
        return (
            f"Cycle month has {month_hours:.0f}h (<{threshold:.0f}). "
            f"Cumulative across client weeks/months is {cumulative_hours:.0f}h "
            f"(reached configured cap)."
        )
    return (
        f"Partial month / mid-month start: {month_hours:.0f}h this month, "
        f"{cumulative_hours:.0f}h cumulative so far "
        f"({threshold:.0f}h may complete over later months)."
    )
