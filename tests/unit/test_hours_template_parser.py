import io

import pytest
from openpyxl import Workbook

from app.services.cycles.hours_template_parser import parse_hours_template


def _xlsx_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_hours_template_requires_hours_by_default():
    content = _xlsx_bytes(
        ["Candidate Name", "Candidate ID", "Client Name", "Month"],
        [["Jane Doe", "ATC-1", "Acme", "2026-08"]],
    )
    with pytest.raises(ValueError, match="Hours Worked"):
        parse_hours_template(content, "hours.xlsx")


def test_parse_placement_template_without_hours():
    content = _xlsx_bytes(
        ["Candidate Name", "Candidate ID", "Client Name", "Month"],
        [["Jane Doe", "ATC-1", "Acme", "2026-08"]],
    )
    rows = parse_hours_template(content, "placement.xlsx", require_hours=False)
    assert len(rows) == 1
    assert rows[0].uploaded_name == "Jane Doe"
    assert rows[0].uploaded_id == "ATC-1"
    assert rows[0].client == "Acme"
    assert rows[0].month == "2026-08"
    assert rows[0].hours == 0.0
