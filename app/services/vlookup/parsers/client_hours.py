"""
Client hours parsers.

Supports:
1. Ampcus QuickBooks invoice export (Memo / Name=Client:code / Qty)
2. Generic flat CSV/Excel with candidate name + hours columns
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.services.vlookup.normalization import (
    extract_person_name,
    normalize_client_name,
    normalize_month_year,
    normalize_name,
)


NOISE_PREFIXES = (
    "total ",
    "service",
    "clin ",
)

WEEK_ENDING_PATTERNS = [
    re.compile(r"^(?P<name>.+?)\s+FOR THE WEEK ENDING OF\s*[:-]?\s*(?P<date>[\d/\-]+)", re.I),
    re.compile(r"^(?P<name>.+?)\s+FOR THE WEEK ENDING OF\s*[:-]?", re.I),
    re.compile(r"^(?P<name>.+?)\s+FOR THE MONTH OF\s+(?P<month>[A-Za-z]{3,9})", re.I),
    re.compile(r"^(?P<name>.+?)\s+FOR THE PERIOD\s*[:-]?\s*(?P<period>.+)$", re.I),
    re.compile(r"^(?P<name>.+?)\s+FOR THE PERIOD\s*/?\s*BY\s*[:-]?\s*(?P<period>.+)$", re.I),
]

MONTH_NAME_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def detect_client_format(df: pd.DataFrame, raw_text: Optional[str] = None) -> str:
    """Return 'ampcus_qb' or 'generic_flat'."""
    cols = {str(c).strip().lower() for c in df.columns}
    # Ampcus QB often has a leading empty column then Type/Date/Num/Memo/Name/Qty
    qb_markers = {"type", "date", "num", "memo", "name", "qty"}
    if qb_markers.issubset(cols) or qb_markers.issubset({c for c in cols if c}):
        return "ampcus_qb"

    # Heuristic on raw text when pandas mangled the empty first column
    if raw_text:
        head = "\n".join(raw_text.splitlines()[:5]).lower()
        if "memo" in head and "qty" in head and "for the week ending" in raw_text.lower()[:5000]:
            return "ampcus_qb"

    # Check first column values for group headers / invoice pattern
    if len(df.columns) >= 5:
        sample = " ".join(str(x) for x in df.head(30).astype(str).values.ravel()).lower()
        if "for the week ending" in sample and "invoice" in sample:
            return "ampcus_qb"

    return "generic_flat"


def parse_client_hours_file(
    file_content: bytes,
    filename: str,
    target_month: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Parse client hours into normalized weekly rows.

    Returns:
        {
          format: str,
          rows: [{candidate_name, client_name, hours_worked, week, month, source_ref}],
          candidate_count: int,
          months_found: [YYYY-MM],
          warnings: [str]
        }
    """
    lower = filename.lower()
    raw_text = None
    if lower.endswith(".csv"):
        raw_text = _decode_bytes(file_content)
        # Prefer raw Ampcus path when QB markers are present
        if _looks_like_ampcus_raw(raw_text):
            return _parse_ampcus_qb_raw(raw_text, target_month=target_month)
        df = _read_csv_bytes(file_content)
    elif lower.endswith((".xlsx", ".xls")):
        df = pd.read_excel(BytesIO(file_content))
    else:
        raise ValueError(f"Unsupported file format: {filename}")

    fmt = detect_client_format(df, raw_text=raw_text)
    if fmt == "ampcus_qb":
        # Fall back to dataframe path if raw wasn't used
        if raw_text and _looks_like_ampcus_raw(raw_text):
            return _parse_ampcus_qb_raw(raw_text, target_month=target_month)
        return _parse_ampcus_qb_dataframe(df, target_month=target_month)
    return _parse_generic_flat(df, target_month=target_month)


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


def _looks_like_ampcus_raw(text: str) -> bool:
    head = "\n".join(text.splitlines()[:3]).lower()
    body = text[:8000].lower()
    return ("memo" in head and "qty" in head) or ("for the week ending" in body and ",invoice," in body)


def _parse_ampcus_qb_raw(text: str, target_month: Optional[str] = None) -> Dict[str, Any]:
    warnings: List[str] = []
    rows: List[Dict[str, Any]] = []
    current_group_name = ""
    skipped_non_candidate = 0

    target = normalize_month_year(target_month) if target_month else ""

    for line_no, line in enumerate(text.splitlines(), start=1):
        raw = line.strip("\n")
        if not raw.strip():
            continue

        # Header
        if line_no == 1 and "memo" in raw.lower() and "qty" in raw.lower():
            continue

        # Group header: no leading comma / not Invoice / not Total alone
        if not raw.startswith(",") and not raw.lower().startswith("service"):
            if raw.lower().startswith("total "):
                continue
            # Candidate section header — name before parenthesis or entire line
            # Format: "NAME (NAME FOR THE WEEK ENDING OF-)" or just "NAME"
            if "(" in raw:
                group = raw.split("(")[0].strip().strip('"')
            else:
                group = raw.strip().strip('"')
            cleaned = _clean_candidate_name(group)
            if cleaned and len(cleaned) > 3:  # Minimum viable name length
                current_group_name = cleaned
            continue

        parts = _split_csv_line(raw)
        # Expected: ['', 'Invoice', date, num, memo, name, qty]
        if len(parts) < 7:
            continue
        row_type = parts[1].strip().lower()
        if row_type != "invoice":
            continue

        date_str = parts[2].strip()
        num = parts[3].strip()
        memo = parts[4].strip().strip('"')
        client_raw = parts[5].strip().strip('"')
        qty_raw = parts[6].strip()

        hours = _to_float(qty_raw)
        if hours is None or hours <= 0:
            continue

        name_from_memo = _extract_name_from_memo(memo)
        # Prefer group header name if memo name appears truncated or is shorter
        # This handles cases where QuickBooks export truncates long names in memo field
        if name_from_memo and current_group_name:
            # If memo name is significantly shorter or appears truncated, use group header
            if len(name_from_memo) < len(current_group_name) and current_group_name.upper().startswith(name_from_memo.upper()):
                candidate_name = current_group_name
            else:
                # Prefer the longer, more complete name
                candidate_name = max(name_from_memo, current_group_name, key=len)
        else:
            candidate_name = name_from_memo or current_group_name
        
        if not candidate_name or _is_noise_name(candidate_name):
            # Expected noise in QB exports — summarize once, do not spam UI
            skipped_non_candidate += 1
            continue

        client_name = client_raw.split(":")[0].strip() if client_raw else ""
        month = _month_from_date(date_str) or _month_from_memo(memo)
        if target and month and month != target:
            continue

        week_label = date_str or num or "Week"
        rows.append({
            "candidate_name": candidate_name,
            "client_name": client_name,
            "hours_worked": hours,
            "week": week_label,
            "month": month,
            "source_ref": num or f"line-{line_no}",
            "normalized_name": normalize_name(candidate_name),
            "normalized_client": normalize_client_name(client_name),
        })

    if skipped_non_candidate:
        warnings.append(
            f"Skipped {skipped_non_candidate} non-candidate invoice row(s) (totals/service lines)."
        )

    return _finalize_result("ampcus_qb", rows, warnings, target)


def _parse_ampcus_qb_dataframe(df: pd.DataFrame, target_month: Optional[str] = None) -> Dict[str, Any]:
    """Fallback dataframe parser for Ampcus-like Excel exports."""
    warnings: List[str] = []
    rows: List[Dict[str, Any]] = []
    target = normalize_month_year(target_month) if target_month else ""

    # Normalize columns
    colmap = {str(c).strip().lower(): c for c in df.columns}
    type_col = colmap.get("type")
    date_col = colmap.get("date")
    memo_col = colmap.get("memo")
    name_col = colmap.get("name")
    qty_col = colmap.get("qty") or colmap.get("quantity")
    num_col = colmap.get("num")

    if not all([memo_col, name_col, qty_col]):
        warnings.append("Ampcus QB columns incomplete; results may be partial")

    current_group_name = ""
    for idx, row in df.iterrows():
        # Detect group header rows (memo/name empty, first non-empty cell is name)
        type_val = str(row.get(type_col, "")).strip() if type_col else ""
        if type_val.lower() != "invoice":
            # Try first string cell as group header
            for cell in row.tolist():
                text = str(cell).strip()
                if text and text.lower() not in ("nan", "none", "service") and not text.lower().startswith("total"):
                    # Extract name before parenthesis if present
                    if "(" in text:
                        cleaned = _clean_candidate_name(text.split("(")[0])
                    else:
                        cleaned = _clean_candidate_name(text)
                    if cleaned and len(cleaned) > 3:  # Minimum viable name length
                        current_group_name = cleaned
                    break
            continue

        memo = str(row.get(memo_col, "")).strip() if memo_col else ""
        client_raw = str(row.get(name_col, "")).strip() if name_col else ""
        hours = _to_float(row.get(qty_col)) if qty_col else None
        date_str = str(row.get(date_col, "")).strip() if date_col else ""
        num = str(row.get(num_col, "")).strip() if num_col else ""

        if hours is None or hours <= 0:
            continue

        name_from_memo = _extract_name_from_memo(memo)
        # Prefer group header name if memo name appears truncated or is shorter
        if name_from_memo and current_group_name:
            if len(name_from_memo) < len(current_group_name) and current_group_name.upper().startswith(name_from_memo.upper()):
                candidate_name = current_group_name
            else:
                candidate_name = max(name_from_memo, current_group_name, key=len)
        else:
            candidate_name = name_from_memo or current_group_name
        
        if not candidate_name or _is_noise_name(candidate_name):
            continue

        client_name = client_raw.split(":")[0].strip() if client_raw else ""
        month = _month_from_date(date_str) or _month_from_memo(memo)
        if target and month and month != target:
            continue

        rows.append({
            "candidate_name": candidate_name,
            "client_name": client_name,
            "hours_worked": hours,
            "week": date_str or num or "Week",
            "month": month,
            "source_ref": num or f"row-{idx}",
            "normalized_name": normalize_name(candidate_name),
            "normalized_client": normalize_client_name(client_name),
        })

    return _finalize_result("ampcus_qb", rows, warnings, target)


def _parse_generic_flat(df: pd.DataFrame, target_month: Optional[str] = None) -> Dict[str, Any]:
    warnings: List[str] = []
    rows: List[Dict[str, Any]] = []
    target = normalize_month_year(target_month) if target_month else ""

    df = df.copy()
    df.columns = [str(c).lower().strip().replace(" ", "_") for c in df.columns]

    name_col = _find_col(df.columns, [
        "candidate_name", "employee_name", "consultant_name", "resource_name",
        "worker_name", "full_name", "name", "employee", "consultant"
    ])
    if not name_col:
        # looser contains search
        for c in df.columns:
            if any(p in c for p in ("candidate", "employee", "consultant", "resource", "worker", "name")):
                # Avoid picking client_name
                if "client" in c:
                    continue
                name_col = c
                break

    if not name_col:
        raise ValueError(
            f"Could not find candidate name column. Found columns: {list(df.columns)}"
        )

    client_col = _find_col(df.columns, ["client_name", "client", "customer", "account"])
    month_col = _find_col(df.columns, ["month", "month_year", "period", "billing_month"])
    id_col = _find_col(df.columns, ["candidate_id", "employee_id", "consultant_id", "id"])

    week_cols = [
        c for c in df.columns
        if any(p in c for p in ("week", "wk")) and any(ch.isdigit() for ch in c)
    ]
    hours_col = None
    if not week_cols:
        hours_col = _find_col(df.columns, [
            "hours_worked", "hours", "total_hours", "hrs", "working_hours", "qty", "quantity"
        ])
        if not hours_col:
            for c in df.columns:
                if any(p in c for p in ("hour", "hrs", "qty")):
                    hours_col = c
                    break

    for idx, row in df.iterrows():
        candidate_name = _clean_candidate_name(str(row.get(name_col, "")))
        if not candidate_name or candidate_name.lower() in ("nan", "none"):
            continue

        client_name = str(row.get(client_col, "")).strip() if client_col else ""
        if client_name.lower() in ("nan", "none"):
            client_name = ""
        month = normalize_month_year(str(row.get(month_col, ""))) if month_col else ""
        if target and month and month != target:
            continue

        candidate_id = str(row.get(id_col, "")).strip() if id_col else ""
        if candidate_id.lower() in ("nan", "none"):
            candidate_id = ""

        if week_cols:
            for week_col in week_cols:
                hours = _to_float(row.get(week_col))
                if hours is None or hours <= 0:
                    continue
                week_num = "".join(ch for ch in week_col if ch.isdigit())
                rows.append({
                    "candidate_name": candidate_name,
                    "candidate_id": candidate_id or None,
                    "client_name": client_name,
                    "hours_worked": hours,
                    "week": f"Week {week_num}" if week_num else week_col,
                    "month": month or target,
                    "source_ref": f"row-{idx}-{week_col}",
                    "normalized_name": normalize_name(candidate_name),
                    "normalized_client": normalize_client_name(client_name),
                })
        elif hours_col:
            hours = _to_float(row.get(hours_col))
            if hours is None or hours <= 0:
                continue
            week_val = "Total"
            for possible in ("week", "week_number", "wk", "week_no"):
                if possible in df.columns:
                    week_val = str(row.get(possible, "Total"))
                    break
            rows.append({
                "candidate_name": candidate_name,
                "candidate_id": candidate_id or None,
                "client_name": client_name,
                "hours_worked": hours,
                "week": week_val,
                "month": month or target,
                "source_ref": f"row-{idx}",
                "normalized_name": normalize_name(candidate_name),
                "normalized_client": normalize_client_name(client_name),
            })

    if not rows:
        warnings.append(
            f"No hours rows parsed from generic flat file. Columns: {list(df.columns)}"
        )

    return _finalize_result("generic_flat", rows, warnings, target)


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


def _split_csv_line(line: str) -> List[str]:
    """Simple CSV split that respects double quotes."""
    parts: List[str] = []
    current = []
    in_quotes = False
    for ch in line:
        if ch == '"':
            in_quotes = not in_quotes
            current.append(ch)
        elif ch == "," and not in_quotes:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts


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


def _is_noise_name(name: str) -> bool:
    n = name.lower().strip()
    if not n:
        return True
    if n.startswith(NOISE_PREFIXES):
        return True
    if "service rendered" in n or n.startswith("clin "):
        return True
    return False


def _month_from_date(date_str: str) -> str:
    if not date_str or date_str.lower() in ("nan", "none"):
        return ""
    text = str(date_str).strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(text.split()[0], fmt)
            return f"{dt.year:04d}-{dt.month:02d}"
        except ValueError:
            continue
    # pandas Timestamp string
    try:
        dt = pd.to_datetime(text)
        return f"{dt.year:04d}-{dt.month:02d}"
    except Exception:
        return ""


def _month_from_memo(memo: str) -> str:
    if not memo:
        return ""
    m = re.search(r"FOR THE MONTH OF\s+([A-Za-z]{3,9})", memo, re.I)
    if m:
        key = m.group(1).lower()
        month_num = MONTH_NAME_MAP.get(key)
        if month_num:
            # Year unknown from memo alone — leave blank
            return ""
    # Date inside memo
    m = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})", memo)
    if m:
        return _month_from_date(m.group(1))
    return ""


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
        if group_by_month:
            key: Tuple[str, ...] = (normalize_name(name), month)
        else:
            key = (normalize_name(name), normalize_client_name(client))
        if key not in groups:
            groups[key] = {
                "candidate_name": name,
                "candidate_id": row.get("candidate_id"),
                "client_name": client,
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
        m = row.get("month") or "unknown"
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
            months_present = [m for m in (g.get("monthly_hours") or {}) if m]
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
