"""Parse the filled Candidate Hours template (Excel/CSV)."""

from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation
from typing import List

from openpyxl import load_workbook

from app.services.cycles.hours_name_matcher import HoursMatchRow


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
}


def parse_hours_template(content: bytes, filename: str = "hours.xlsx") -> List[HoursMatchRow]:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        return _parse_csv(content)
    return _parse_xlsx(content)


def _map_headers(headers: List[str]) -> dict:
    mapping = {}
    for idx, header in enumerate(headers):
        alias = COLUMN_ALIASES.get(_header_key(header))
        if alias and alias not in mapping:
            mapping[alias] = idx
    missing = [label for label in ("name", "id", "client", "hours", "month") if label not in mapping]
    if missing:
        raise ValueError(
            "Hours file is missing required columns: Candidate Name, Candidate Start ID, Client Name, Hours Worked, Month"
        )
    return mapping


def _rows_from_values(headers: List[str], data_rows: List[List[object]]) -> List[HoursMatchRow]:
    mapping = _map_headers(headers)
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
        raise ValueError("No data rows found in the hours file")
    return out


def _parse_xlsx(content: bytes) -> List[HoursMatchRow]:
    workbook = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise ValueError("Hours Excel file is empty")
    headers = [_cell(v) for v in rows[0]]
    return _rows_from_values(headers, [list(r) for r in rows[1:]])


def _parse_csv(content: bytes) -> List[HoursMatchRow]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise ValueError("Hours CSV file is empty")
    return _rows_from_values(rows[0], rows[1:])
