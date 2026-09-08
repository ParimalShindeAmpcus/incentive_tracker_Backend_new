"""Parse the filled Candidate Hours template (Excel/CSV)."""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from openpyxl import load_workbook

from app.services.cycles.hours_name_matcher import HoursMatchRow

_MONTH_NAME_TO_INDEX = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


def _header_key(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _hours(value: object) -> Decimal:
    raw = _cell(value).replace(",", "")
    if not raw:
        return Decimal("0")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return Decimal("0")


def normalize_month_key(value: object) -> str:
    """Normalize month values like Aug-26 / September 2026 / 2026-08 to YYYY-MM."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return f"{value.year}-{value.month:02d}"
    if isinstance(value, date):
        return f"{value.year}-{value.month:02d}"
    if isinstance(value, (int, float)):
        # Excel serial date (approx)
        try:
            from openpyxl.utils.datetime import from_excel

            dt = from_excel(value)
            return f"{dt.year}-{dt.month:02d}"
        except Exception:
            return ""

    raw = _cell(value)
    if not raw or re.fullmatch(r"#+", raw):
        return ""
    if re.fullmatch(r"\d{4}-\d{2}", raw):
        return raw

    named = re.fullmatch(r"([A-Za-z]+)\s*[-/., ]\s*(\d{4})", raw)
    if named:
        idx = _MONTH_NAME_TO_INDEX.get(named.group(1).lower())
        if idx:
            return f"{named.group(2)}-{idx:02d}"

    named_yy = re.fullmatch(r"([A-Za-z]+)\s*[-/., ]\s*(\d{2})", raw)
    if named_yy:
        idx = _MONTH_NAME_TO_INDEX.get(named_yy.group(1).lower())
        if idx:
            yy = int(named_yy.group(2))
            year = 2000 + yy if yy < 100 else yy
            return f"{year}-{idx:02d}"

    ym = re.fullmatch(r"(\d{4})[/.-](\d{1,2})", raw)
    if ym:
        m = int(ym.group(2))
        if 1 <= m <= 12:
            return f"{ym.group(1)}-{m:02d}"

    my = re.fullmatch(r"(\d{1,2})[/.-](\d{4})", raw)
    if my:
        m = int(my.group(1))
        if 1 <= m <= 12:
            return f"{my.group(2)}-{m:02d}"

    m_yy = re.fullmatch(r"(\d{1,2})[/.-](\d{2})", raw)
    if m_yy:
        m = int(m_yy.group(1))
        yy = int(m_yy.group(2))
        if 1 <= m <= 12:
            return f"{2000 + yy}-{m:02d}"

    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            return f"{dt.year}-{dt.month:02d}"
        except ValueError:
            continue
    return ""


def assert_rows_match_cycle_month(rows: List[HoursMatchRow], cycle_month: Optional[str]) -> None:
    """Reject uploads whose Month column does not match the cycle incentive month."""
    expected = (cycle_month or "").strip()
    if not expected:
        raise ValueError("Cycle incentive month is missing. Recreate the cycle and try again.")

    found: set[str] = set()
    missing = 0
    wrong = 0

    for row in rows:
        raw = _cell(row.month)
        mk = normalize_month_key(raw)
        if not mk:
            missing += 1
            continue
        found.add(mk)
        if mk != expected:
            wrong += 1

    if missing or wrong:
        file_months = sorted(m for m in found if m != expected)
        file_label = ", ".join(file_months) if file_months else "unknown/missing"
        raise ValueError(
            f"Wrong month in file. Cycle month is {expected}, but file has {file_label}."
        )


COLUMN_ALIASES = {
    "candidate name": "name",
    "candidate": "name",
    "consultant": "name",
    "name": "name",
    "candidate start id": "id",
    "candidate id": "id",
    "start id": "id",
    "id": "id",
    "client name": "client",
    "client": "client",
    "hours worked": "hours",
    "hours": "hours",
    "month": "month",
    "period": "month",
    "billing month": "month",
    "incentive month": "month",
}


def parse_hours_template(
    content: bytes,
    filename: str = "hours.xlsx",
    *,
    require_hours: bool = True,
) -> List[HoursMatchRow]:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        return _parse_csv(content, require_hours=require_hours)
    return _parse_xlsx(content, require_hours=require_hours)


def _map_headers(headers: List[str], *, require_hours: bool = True) -> dict:
    mapping = {}
    for idx, header in enumerate(headers):
        alias = COLUMN_ALIASES.get(_header_key(header))
        if alias and alias not in mapping:
            mapping[alias] = idx
    # Month is required for all hours/placement uploads so cycle-month validation can run.
    required = ("name", "id", "client", "month")
    if require_hours:
        required = ("name", "id", "hours", "month")
    labels = {
        "name": "Candidate Name",
        "id": "Candidate ID",
        "hours": "Hours Worked",
        "client": "Client Name",
        "month": "Month",
    }
    missing = [labels[label] for label in required if label not in mapping]
    if missing:
        kind = "Hours file" if require_hours else "Placement file"
        raise ValueError(f"{kind} is missing required columns: {', '.join(missing)}")
    return mapping


def _rows_from_values(
    headers: List[str],
    data_rows: List[List[object]],
    *,
    require_hours: bool = True,
) -> List[HoursMatchRow]:
    mapping = _map_headers(headers, require_hours=require_hours)
    out: List[HoursMatchRow] = []
    for offset, values in enumerate(data_rows, start=2):
        def take(key: str) -> str:
            idx = mapping.get(key)
            if idx is None or idx >= len(values):
                return ""
            return _cell(values[idx])

        name = take("name")
        ident = take("id")
        if not name and not ident:
            continue
        hours_raw = None
        if "hours" in mapping:
            hours_idx = mapping["hours"]
            hours_raw = values[hours_idx] if hours_idx < len(values) else None
        out.append(
            HoursMatchRow(
                uploaded_name=name,
                uploaded_id=ident,
                client=take("client"),
                hours=float(_hours(hours_raw)),
                month=take("month"),
                source_row=offset,
            )
        )
    if not out:
        kind = "hours file" if require_hours else "placement file"
        raise ValueError(f"No data rows found in the {kind}")
    return out


def _parse_xlsx(content: bytes, *, require_hours: bool = True) -> List[HoursMatchRow]:
    workbook = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise ValueError("Hours Excel file is empty")
    headers = [_cell(v) for v in rows[0]]
    return _rows_from_values(headers, [list(r) for r in rows[1:]], require_hours=require_hours)


def _parse_csv(content: bytes, *, require_hours: bool = True) -> List[HoursMatchRow]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise ValueError("Hours CSV file is empty")
    return _rows_from_values(rows[0], rows[1:], require_hours=require_hours)
