"""
Nashik hierarchy continuation, employment status, and top-2 role selection.

Source of truth:
  app/services/incentives/nashik_rules.py
  app/services/incentives/nashik_calculator.py

Rules:
  - LEFT / NOTICE => person ineligible; hierarchy continues for others
  - ALL roles (including Recruiter) compete for max 2 per person by ROLE_PRIORITY
  - Role selection happens AFTER status filtering
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.incentives.nashik_calculator import (
    CycleWindow,
    PlacementInput,
    calculate_nashik_placement,
)
from app.services.incentives.nashik_rules import (
    LEADERSHIP_ONE_TIME,
    MAX_ROLES_PER_PERSON,
    ROLE_PRIORITY,
    TEAM_LEAD_BASE,
    normalize_person,
)

WINDOW = CycleWindow(start=date(2026, 8, 1), end=date(2026, 8, 31))


def _p(**kwargs) -> PlacementInput:
    data = dict(
        candidate_pk=1,
        external_id="NASH-TEST",
        name="Test Candidate",
        contract_type="W2",
        candidate_source="Ampcus Inc",
        organization="Ampcus Inc",
        recruiter_location="Nashik",
        start_date=date(2026, 1, 15),
        end_date=None,
        margin=Decimal("8"),
        hours=Decimal("160"),
        recruiter="Recruiter Active",
        team_lead="Team Lead Active",
        crm="CRM Active",
        manager="Manager Active",
        senior_manager=None,
        associate_director=None,
        center_head=None,
        avp=None,
        incentive_active=True,
        project_ended=False,
    )
    data.update(kwargs)
    return PlacementInput(**data)


def _status(*pairs: tuple[str, str]) -> dict[str, str]:
    return {normalize_person(name): status.upper() for name, status in pairs}


def _eligible(lines):
    return [l for l in lines if l.eligible and l.amount > 0]


def _eligible_roles(lines, person: str | None = None):
    out = []
    for line in lines:
        if not line.eligible or line.amount <= 0:
            continue
        if person is not None and line.person != person:
            continue
        out.append(line.role)
    return out


def _amount(lines, role: str, person: str | None = None) -> Decimal:
    total = Decimal("0")
    for line in lines:
        if line.role != role or not line.eligible:
            continue
        if person is not None and line.person != person:
            continue
        total += line.amount
    return total


def _by_role(lines, role: str):
    return [l for l in lines if l.role == role]


# ---------------------------------------------------------------------------
# Test N / baseline — all ACTIVE
# ---------------------------------------------------------------------------
def test_N_active_baseline_amounts_unchanged():
    lines = calculate_nashik_placement(
        _p(
            recruiter="Rec Active",
            team_lead="TL Active",
            manager="Mgr Active",
            crm="CRM Active",
            center_head="CH Active",
            avp="AVP Active",
        ),
        WINDOW,
        employment_status=_status(
            ("Rec Active", "ACTIVE"),
            ("TL Active", "ACTIVE"),
            ("Mgr Active", "ACTIVE"),
            ("CRM Active", "ACTIVE"),
            ("CH Active", "ACTIVE"),
            ("AVP Active", "ACTIVE"),
        ),
    )
    assert _amount(lines, "Recruiter", "Rec Active") == Decimal("2000")
    assert _amount(lines, "Team Lead", "TL Active") == TEAM_LEAD_BASE
    assert _amount(lines, "Manager", "Mgr Active") == LEADERSHIP_ONE_TIME["Manager"]
    assert _amount(lines, "CRM", "CRM Active") == LEADERSHIP_ONE_TIME["CRM"]
    assert _amount(lines, "Center Head", "CH Active") == LEADERSHIP_ONE_TIME["Center Head"]
    assert _amount(lines, "AVP", "AVP Active") == LEADERSHIP_ONE_TIME["AVP"]
    assert len(_eligible(lines)) == 6


# ---------------------------------------------------------------------------
# Test A — Recruiter LEFT
# ---------------------------------------------------------------------------
def test_A_recruiter_left_hierarchy_continues():
    lines = calculate_nashik_placement(
        _p(recruiter="Rec Left", team_lead="TL Active", manager="Mgr Active", crm="CRM Active"),
        WINDOW,
        employment_status=_status(
            ("Rec Left", "LEFT"),
            ("TL Active", "ACTIVE"),
            ("Mgr Active", "ACTIVE"),
            ("CRM Active", "ACTIVE"),
        ),
    )
    assert _amount(lines, "Recruiter", "Rec Left") == Decimal("0")
    rec = _by_role(lines, "Recruiter")[0]
    assert rec.eligible is False
    assert rec.reason == "COORDINATOR_LEFT"
    assert _amount(lines, "Team Lead", "TL Active") == TEAM_LEAD_BASE
    assert _amount(lines, "Manager", "Mgr Active") == LEADERSHIP_ONE_TIME["Manager"]
    assert _amount(lines, "CRM", "CRM Active") == LEADERSHIP_ONE_TIME["CRM"]
    # Candidate / hierarchy not discarded
    assert any(l.role == "Recruiter" for l in lines)
    assert len(lines) >= 4


# ---------------------------------------------------------------------------
# Test B — Manager LEFT
# ---------------------------------------------------------------------------
def test_B_manager_left_both_sides_continue():
    lines = calculate_nashik_placement(
        _p(
            recruiter="Rec Active",
            team_lead="TL Active",
            manager="Mgr Left",
            crm="CRM Active",
            center_head="CH Active",
        ),
        WINDOW,
        employment_status=_status(
            ("Rec Active", "ACTIVE"),
            ("TL Active", "ACTIVE"),
            ("Mgr Left", "LEFT"),
            ("CRM Active", "ACTIVE"),
            ("CH Active", "ACTIVE"),
        ),
    )
    assert _amount(lines, "Manager", "Mgr Left") == Decimal("0")
    assert any(l.role == "Manager" and l.reason == "COORDINATOR_LEFT" for l in lines)
    assert _amount(lines, "Recruiter", "Rec Active") == Decimal("2000")
    assert _amount(lines, "Team Lead", "TL Active") == TEAM_LEAD_BASE
    assert _amount(lines, "CRM", "CRM Active") == LEADERSHIP_ONE_TIME["CRM"]
    assert _amount(lines, "Center Head", "CH Active") == LEADERSHIP_ONE_TIME["Center Head"]


# ---------------------------------------------------------------------------
# Test C — Team Lead LEFT
# ---------------------------------------------------------------------------
def test_C_team_lead_left_others_continue():
    lines = calculate_nashik_placement(
        _p(recruiter="Rec Active", team_lead="TL Left", manager="Mgr Active", crm="CRM Active"),
        WINDOW,
        employment_status=_status(
            ("Rec Active", "ACTIVE"),
            ("TL Left", "LEFT"),
            ("Mgr Active", "ACTIVE"),
            ("CRM Active", "ACTIVE"),
        ),
    )
    assert _amount(lines, "Team Lead", "TL Left") == Decimal("0")
    assert _amount(lines, "Recruiter", "Rec Active") == Decimal("2000")
    assert _amount(lines, "Manager", "Mgr Active") == LEADERSHIP_ONE_TIME["Manager"]
    assert _amount(lines, "CRM", "CRM Active") == LEADERSHIP_ONE_TIME["CRM"]


# ---------------------------------------------------------------------------
# Test D — CRM LEFT
# ---------------------------------------------------------------------------
def test_D_crm_left_others_continue():
    lines = calculate_nashik_placement(
        _p(recruiter="Rec Active", team_lead="TL Active", manager="Mgr Active", crm="CRM Left"),
        WINDOW,
        employment_status=_status(
            ("Rec Active", "ACTIVE"),
            ("TL Active", "ACTIVE"),
            ("Mgr Active", "ACTIVE"),
            ("CRM Left", "LEFT"),
        ),
    )
    assert _amount(lines, "CRM", "CRM Left") == Decimal("0")
    assert _amount(lines, "Recruiter") == Decimal("2000")
    assert _amount(lines, "Team Lead") == TEAM_LEAD_BASE
    assert _amount(lines, "Manager") == LEADERSHIP_ONE_TIME["Manager"]


# ---------------------------------------------------------------------------
# Test E — Nitin Recruiter + Manager + CRM
# ---------------------------------------------------------------------------
def test_E_nitin_rec_mgr_crm_top_two_excludes_recruiter():
    person = "Nitin Giri"
    lines = calculate_nashik_placement(
        _p(recruiter=person, team_lead="Other TL", manager=person, crm=person),
        WINDOW,
        employment_status=_status((person, "ACTIVE"), ("Other TL", "ACTIVE")),
    )
    nitin_roles = sorted(_eligible_roles(lines, person))
    assert nitin_roles == ["CRM", "Manager"]
    assert _amount(lines, "Recruiter", person) == Decimal("0")
    assert _amount(lines, "Manager", person) == LEADERSHIP_ONE_TIME["Manager"]
    assert _amount(lines, "CRM", person) == LEADERSHIP_ONE_TIME["CRM"]
    assert len([l for l in _eligible(lines) if l.person == person]) == 2


# ---------------------------------------------------------------------------
# Test F — Nitin Recruiter + Team Lead + Manager
# ---------------------------------------------------------------------------
def test_F_nitin_rec_tl_mgr_selects_manager_and_tl():
    person = "Nitin Giri"
    lines = calculate_nashik_placement(
        _p(recruiter=person, team_lead=person, manager=person, crm="Other CRM"),
        WINDOW,
        employment_status=_status((person, "ACTIVE"), ("Other CRM", "ACTIVE")),
    )
    roles = set(_eligible_roles(lines, person))
    assert roles == {"Manager", "Team Lead"}
    assert _amount(lines, "Recruiter", person) == Decimal("0")
    assert len(roles) == MAX_ROLES_PER_PERSON


# ---------------------------------------------------------------------------
# Test G — Nitin Recruiter + Manager
# ---------------------------------------------------------------------------
def test_G_nitin_rec_and_manager_both_selected():
    person = "Nitin Giri"
    lines = calculate_nashik_placement(
        _p(recruiter=person, team_lead="Other TL", manager=person, crm="Other CRM"),
        WINDOW,
        employment_status=_status(
            (person, "ACTIVE"),
            ("Other TL", "ACTIVE"),
            ("Other CRM", "ACTIVE"),
        ),
    )
    roles = set(_eligible_roles(lines, person))
    assert roles == {"Manager", "Recruiter"}
    assert _amount(lines, "Manager", person) == LEADERSHIP_ONE_TIME["Manager"]
    assert _amount(lines, "Recruiter", person) == Decimal("2000")


# ---------------------------------------------------------------------------
# Test H — Nitin Recruiter + CRM
# ---------------------------------------------------------------------------
def test_H_nitin_rec_and_crm_both_selected():
    person = "Nitin Giri"
    lines = calculate_nashik_placement(
        _p(recruiter=person, team_lead="Other TL", manager="Other Mgr", crm=person),
        WINDOW,
        employment_status=_status(
            (person, "ACTIVE"),
            ("Other TL", "ACTIVE"),
            ("Other Mgr", "ACTIVE"),
        ),
    )
    roles = set(_eligible_roles(lines, person))
    assert roles == {"CRM", "Recruiter"}
    assert _amount(lines, "CRM", person) == LEADERSHIP_ONE_TIME["CRM"]
    assert _amount(lines, "Recruiter", person) == Decimal("2000")


# ---------------------------------------------------------------------------
# Test I — Nitin all roles
# ---------------------------------------------------------------------------
def test_I_nitin_all_roles_avp_and_associate_director_only():
    person = "Nitin Giri"
    lines = calculate_nashik_placement(
        _p(
            recruiter=person,
            team_lead=person,
            manager=person,
            crm=person,
            senior_manager=person,
            associate_director=person,
            center_head=person,
            avp=person,
        ),
        WINDOW,
        employment_status=_status((person, "ACTIVE")),
    )
    roles = set(_eligible_roles(lines, person))
    assert roles == {"AVP", "Associate Director"}
    assert len(roles) == 2
    assert _amount(lines, "Recruiter", person) == Decimal("0")
    assert _amount(lines, "Manager", person) == Decimal("0")
    assert _amount(lines, "CRM", person) == Decimal("0")
    assert _amount(lines, "Team Lead", person) == Decimal("0")
    assert _amount(lines, "Center Head", person) == Decimal("0")
    assert _amount(lines, "Senior Manager", person) == Decimal("0")


# ---------------------------------------------------------------------------
# Test J — LEFT higher-priority role then remaining people continue
# ---------------------------------------------------------------------------
def test_J_left_avp_then_manager_and_crm_selected():
    lines = calculate_nashik_placement(
        _p(
            recruiter="Rec Active",
            team_lead=None,
            manager="Mgr Active",
            crm="CRM Active",
            avp="AVP Left",
        ),
        WINDOW,
        employment_status=_status(
            ("AVP Left", "LEFT"),
            ("Mgr Active", "ACTIVE"),
            ("CRM Active", "ACTIVE"),
            ("Rec Active", "ACTIVE"),
        ),
    )
    assert _amount(lines, "AVP", "AVP Left") == Decimal("0")
    assert _amount(lines, "Manager", "Mgr Active") == LEADERSHIP_ONE_TIME["Manager"]
    assert _amount(lines, "CRM", "CRM Active") == LEADERSHIP_ONE_TIME["CRM"]
    assert _amount(lines, "Recruiter", "Rec Active") == Decimal("2000")


def test_J_same_person_left_higher_role_override_then_top_two():
    """Role-scoped LEFT on AVP leaves Manager+CRM as the top two for Nitin."""
    person = "Nitin Giri"
    key = normalize_person(person)
    lines = calculate_nashik_placement(
        _p(
            recruiter=person,
            team_lead=None,
            manager=person,
            crm=person,
            avp=person,
        ),
        WINDOW,
        employment_status={
            key: "ACTIVE",
            f"avp|{key}": "LEFT",
        },
    )
    assert set(_eligible_roles(lines, person)) == {"Manager", "CRM"}
    assert _amount(lines, "AVP", person) == Decimal("0")
    assert _amount(lines, "Recruiter", person) == Decimal("0")


# ---------------------------------------------------------------------------
# Test K — Manager unavailable then CRM + Recruiter (selection after filter)
# ---------------------------------------------------------------------------
def test_K_nitin_manager_left_selects_crm_and_recruiter():
    """
    Manager role marked LEFT while Recruiter/CRM remain ACTIVE for Nitin.
    Uses optional role-scoped status keys ("manager|nitin giri"); cycle_engine
    still passes person-level Coordinator Master status only.
    """
    person = "Nitin Giri"
    key = normalize_person(person)
    lines = calculate_nashik_placement(
        _p(recruiter=person, team_lead=None, manager=person, crm=person),
        WINDOW,
        employment_status={
            key: "ACTIVE",
            f"manager|{key}": "LEFT",
            f"recruiter|{key}": "ACTIVE",
            f"crm|{key}": "ACTIVE",
        },
    )
    roles = set(_eligible_roles(lines, person))
    assert roles == {"CRM", "Recruiter"}
    assert _amount(lines, "Manager", person) == Decimal("0")
    assert any(l.role == "Manager" and l.reason == "COORDINATOR_LEFT" for l in lines)


def test_K_person_level_left_excludes_all_roles_for_nitin():
    """Coordinator Master person-level LEFT excludes every role for that person."""
    person = "Nitin Giri"
    lines = calculate_nashik_placement(
        _p(recruiter=person, manager=person, crm=person),
        WINDOW,
        employment_status=_status((person, "LEFT")),
    )
    assert _eligible_roles(lines, person) == []
    assert all((not l.eligible or l.amount == 0) for l in lines if l.person == person)


# ---------------------------------------------------------------------------
# Test L — LEFT with qualifying hours
# ---------------------------------------------------------------------------
def test_L_left_with_160_hours_still_excluded():
    lines = calculate_nashik_placement(
        _p(recruiter="Rec Left", team_lead="TL Active", hours=Decimal("160")),
        WINDOW,
        employment_status=_status(("Rec Left", "LEFT"), ("TL Active", "ACTIVE")),
    )
    assert _amount(lines, "Recruiter", "Rec Left") == Decimal("0")
    assert _amount(lines, "Team Lead", "TL Active") == TEAM_LEAD_BASE


# ---------------------------------------------------------------------------
# Test M — NOTICE follows repository rule (not eligible)
# ---------------------------------------------------------------------------
def test_M_notice_not_eligible_like_client_engine():
    lines = calculate_nashik_placement(
        _p(recruiter="Rec Notice", team_lead="TL Active", manager="Mgr Active", crm="CRM Active"),
        WINDOW,
        employment_status=_status(
            ("Rec Notice", "NOTICE"),
            ("TL Active", "ACTIVE"),
            ("Mgr Active", "ACTIVE"),
            ("CRM Active", "ACTIVE"),
        ),
    )
    assert _amount(lines, "Recruiter", "Rec Notice") == Decimal("0")
    assert any(l.role == "Recruiter" and l.reason == "COORDINATOR_ON_NOTICE" for l in lines)
    assert _amount(lines, "Team Lead", "TL Active") == TEAM_LEAD_BASE
    assert _amount(lines, "Manager", "Mgr Active") == LEADERSHIP_ONE_TIME["Manager"]
    assert _amount(lines, "CRM", "CRM Active") == LEADERSHIP_ONE_TIME["CRM"]


# ---------------------------------------------------------------------------
# Per-employee top-2 (not global)
# ---------------------------------------------------------------------------
def test_top_two_is_per_employee_not_global():
    lines = calculate_nashik_placement(
        _p(
            recruiter="Rahul",
            team_lead="Rahul",
            manager="Nitin",
            crm="Nitin",
        ),
        WINDOW,
        employment_status=_status(("Rahul", "ACTIVE"), ("Nitin", "ACTIVE")),
    )
    assert set(_eligible_roles(lines, "Nitin")) == {"Manager", "CRM"}
    assert set(_eligible_roles(lines, "Rahul")) == {"Team Lead", "Recruiter"}


# ---------------------------------------------------------------------------
# Missing hierarchy / zero hours
# ---------------------------------------------------------------------------
def test_missing_hierarchy_no_crash():
    lines = calculate_nashik_placement(
        _p(recruiter="Rec Active", team_lead="TL Active", manager=None, crm=None),
        WINDOW,
        employment_status=_status(("Rec Active", "ACTIVE"), ("TL Active", "ACTIVE")),
    )
    assert _amount(lines, "Recruiter") == Decimal("2000")
    assert _amount(lines, "Team Lead") == TEAM_LEAD_BASE
    assert _by_role(lines, "Manager") == []


def test_zero_hours_no_full_incentive():
    lines = calculate_nashik_placement(
        _p(recruiter="Rec Active", team_lead="TL Active", manager="Mgr Active", hours=Decimal("0")),
        WINDOW,
        employment_status=_status(
            ("Rec Active", "ACTIVE"),
            ("TL Active", "ACTIVE"),
            ("Mgr Active", "ACTIVE"),
        ),
    )
    assert _amount(lines, "Recruiter") == Decimal("0")
    assert _amount(lines, "Team Lead") == Decimal("0")
    mgr = _by_role(lines, "Manager")
    assert mgr and mgr[0].eligible is False


def test_role_priority_includes_recruiter_last():
    assert ROLE_PRIORITY[0] == "AVP"
    assert ROLE_PRIORITY[-1] == "Recruiter"
    assert ROLE_PRIORITY.index("Manager") < ROLE_PRIORITY.index("CRM")
    assert ROLE_PRIORITY.index("CRM") < ROLE_PRIORITY.index("Team Lead")
    assert ROLE_PRIORITY.index("Team Lead") < ROLE_PRIORITY.index("Recruiter")
    assert MAX_ROLES_PER_PERSON == 2


def test_recruiter_only_still_paid_when_active():
    lines = calculate_nashik_placement(
        _p(recruiter="Only Rec", team_lead=None, manager=None, crm=None),
        WINDOW,
        employment_status=_status(("Only Rec", "ACTIVE")),
    )
    assert _amount(lines, "Recruiter", "Only Rec") == Decimal("2000")
