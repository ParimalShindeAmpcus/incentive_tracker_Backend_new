"""Nashik Hours Template / Smart Match scope from Organisation + Recruiter Location."""

from types import SimpleNamespace

from app.services.incentives.nashik_rules import is_nashik_hours_scope
from app.services.vlookup.vlookup_service import _restrict_templates_to_nashik_division


def test_nashik_org_and_location_included():
    assert is_nashik_hours_scope(
        organization="Ampcus Inc",
        recruiter_location="Nashik",
    )
    assert is_nashik_hours_scope(
        organization="Bravens Inc",
        recruiter_location="ND",
    )


def test_sambhaji_location_excluded_even_for_nashik_org():
    assert not is_nashik_hours_scope(
        organization="Ampcus Inc",
        recruiter_location="Sambhaji Nagar",
    )


def test_ampcus_tech_orgs_excluded():
    assert not is_nashik_hours_scope(
        organization="Ampcus Tech Client",
        recruiter_location="Nashik",
    )
    assert not is_nashik_hours_scope(
        organization="Ampcus Tech Inhouse",
        recruiter_location="Nashik",
    )


def test_restrict_templates_drops_known_non_nashik_and_keeps_unknown(monkeypatch):
    nashik = SimpleNamespace(
        external_candidate_id="NASHIK-1",
        start_id=None,
        activity_id=None,
        organization="Ampcus Inc",
        candidate_source="Ampcus Inc",
        recruiter_location="Nashik",
    )
    sambhaji = SimpleNamespace(
        external_candidate_id="SN-1",
        start_id=None,
        activity_id=None,
        organization="Ampcus Inc",
        candidate_source="Ampcus Inc",
        recruiter_location="Sambhaji Nagar",
    )

    monkeypatch.setattr(
        "app.services.vlookup.vlookup_service.candidate_repository.list_all_candidates",
        lambda _db: [nashik, sambhaji],
    )

    templates = [
        SimpleNamespace(candidate_id="NASHIK-1"),
        SimpleNamespace(candidate_id="SN-1"),
        SimpleNamespace(candidate_id="UNKNOWN-99"),
    ]
    kept, skipped = _restrict_templates_to_nashik_division(None, templates)
    kept_ids = {row.candidate_id for row in kept}
    assert kept_ids == {"NASHIK-1", "UNKNOWN-99"}
    assert skipped == 1
