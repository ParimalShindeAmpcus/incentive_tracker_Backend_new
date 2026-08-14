import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.cycles.cycle_service import _export_row


def test_export_row_uses_candidate_master_fields():
    cycle = SimpleNamespace(incentive_month="2026-08")
    line = SimpleNamespace(
        person="Amit Ohol",
        role="Recruiter",
        incentive_type="RECURRING",
        candidate_name="Aisha Mayes",
        hours=Decimal("160"),
        amount=Decimal("3500"),
        margin=Decimal("12"),
        explanation_json=None,
        eligible=True,
    )
    cand = SimpleNamespace(
        start_date=date(2026, 1, 1),
        contract_type="C2C",
        margin=Decimal("12"),
        start_id="12345",
        external_candidate_id="12345",
        candidate_source="Ampcus Inc",
        organization=None,
        crm="David",
        center_head=None,
        associate_director=None,
        manager=None,
        team_lead=None,
    )
    row = _export_row(cycle, line, cand)
    assert row[2] == "12345"
    assert row[4] == "2026-01-01"
    assert row[6] == "C2C"
    assert row[7] == 12.0


def test_export_row_falls_back_to_explanation_json():
    cycle = SimpleNamespace(incentive_month="2026-08")
    line = SimpleNamespace(
        person="Amit Ohol",
        role="Recruiter",
        incentive_type="RECURRING",
        candidate_name="Aisha Mayes",
        hours=Decimal("160"),
        amount=Decimal("3500"),
        margin=None,
        explanation_json=json.dumps(
            {
                "start_date": "2026-01-01",
                "contract_type": "C2C",
                "margin_per_hour": 12.0,
                "candidate_id": "12345",
                "candidate_source": "Ampcus Inc",
            }
        ),
        eligible=True,
    )
    row = _export_row(cycle, line, None)
    assert row[2] == "12345"
    assert row[4] == "2026-01-01"
    assert row[6] == "C2C"
    assert row[7] == 12.0
