"""Unit tests for reports service mapping helpers."""

from datetime import date
from decimal import Decimal

from app.services.reports.reports_service import (
    _coordinator_type_label,
    _incentive_type_label,
    _month_as_date,
    _team_label,
    _to_row,
)


def test_coordinator_type_labels():
    assert _coordinator_type_label("CRM") == "Crm"
    assert _coordinator_type_label("Associate Director") == "Asso Director"
    assert _coordinator_type_label("Recruiter") == "Recruiter"


def test_incentive_type_labels():
    assert _incentive_type_label("RECURRING") == "Recurring"
    assert _incentive_type_label("ONE_TIME") == "One-time"


def test_month_as_date():
    assert _month_as_date("2026-02") == "2026-02-01"


def test_team_prefers_crm():
    row = {
        "crm": "Majid Khan",
        "center_head": "",
        "associate_director": "",
        "manager": "Someone",
        "senior_manager": "",
        "team_lead": "Nitin Giri",
    }
    assert _team_label(row) == "Majid Khan"


def test_to_row_shape():
    row = {
        "person": "Amit William Ohol",
        "role": "Recruiter",
        "line_candidate_name": "Aisha Mayes",
        "amount": Decimal("2500.40"),
        "hours": Decimal("160"),
        "line_margin": Decimal("12"),
        "incentive_type": "RECURRING",
        "cycle_id": 1,
        "cycle_name": "Demo",
        "division": "nashik",
        "incentive_month": "2026-02",
        "external_candidate_id": "AMSUB24-2495",
        "candidate_name": "Aisha Mayes",
        "start_date": date(2023, 10, 10),
        "contract_type": "C2C",
        "candidate_source": "Ampcus Inc",
        "organization": "Ampcus Inc",
        "candidate_margin": Decimal("12"),
        "crm": "Majid Khan",
        "center_head": None,
        "associate_director": None,
        "manager": None,
        "senior_manager": None,
        "team_lead": "Nitin Giri",
    }
    mapped = _to_row(row)
    assert mapped.coordinator_name == "Amit William Ohol"
    assert mapped.candidate_id == "AMSUB24-2495"
    assert mapped.month == "2026-02-01"
    assert mapped.incentive_amount_inr == Decimal("2500")
    assert mapped.incentive_type == "Recurring"
    assert mapped.team == "Majid Khan"
