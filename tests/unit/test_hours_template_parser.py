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


def test_normalize_month_key_formats():
    from app.services.cycles.hours_template_parser import (
        assert_rows_match_cycle_month,
        normalize_month_key,
    )
    from app.services.cycles.hours_name_matcher import HoursMatchRow

    assert normalize_month_key("26-Sep", fallback_year=2026) == "2026-09"
    assert normalize_month_key("26 Sep", fallback_year=2026) == "2026-09"
    assert normalize_month_key("9/26/2026") == "2026-09"
    assert normalize_month_key("26/9/2026") == "2026-09"
    assert normalize_month_key("2026-09-26") == "2026-09"
    assert normalize_month_key("2026-09-26 00:00:00") == "2026-09"
    assert normalize_month_key("September 26, 2026") == "2026-09"
    assert normalize_month_key("26 September 2026") == "2026-09"
    assert normalize_month_key("September 2026") == "2026-09"
    assert normalize_month_key("Sep-26") == "2026-09"
    assert normalize_month_key("2026-09") == "2026-09"
    assert normalize_month_key("invalid_date") == ""

    # Test assert_rows_match_cycle_month succeeds on diverse formats matching 2026-09
    sample_rows = [
        HoursMatchRow(uploaded_name="A", uploaded_id="1", client="C", hours=160, month="26-Sep"),
        HoursMatchRow(uploaded_name="B", uploaded_id="2", client="C", hours=160, month="9/26/2026"),
        HoursMatchRow(uploaded_name="C", uploaded_id="3", client="C", hours=160, month="26/9/2026"),
        HoursMatchRow(uploaded_name="D", uploaded_id="4", client="C", hours=160, month="2026-09-26"),
        HoursMatchRow(uploaded_name="E", uploaded_id="5", client="C", hours=160, month="September 26, 2026"),
    ]
    assert_rows_match_cycle_month(sample_rows, "2026-09")

    # Mismatch throws ValueError
    with pytest.raises(ValueError, match="Wrong month in file"):
        mismatch_rows = [
            HoursMatchRow(uploaded_name="A", uploaded_id="1", client="C", hours=160, month="2026-08-01")
        ]
        assert_rows_match_cycle_month(mismatch_rows, "2026-09")
