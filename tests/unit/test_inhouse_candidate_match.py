"""In-House membership must not auto-include Nashik FTE / bare FULLTIME."""
from __future__ import annotations

from app.services.cycles.division_resolver import resolve_candidate_division
from app.services.cycles.engines.ampcus_inhouse import is_ampcus_inhouse_candidate


def test_explicit_division_and_org():
    assert is_ampcus_inhouse_candidate(division="ampcusTechInhouse")
    assert is_ampcus_inhouse_candidate(organization="Ampcus Tech Inhouse")
    assert is_ampcus_inhouse_candidate(contract_type="INHOUSE")


def test_fulltime_alone_is_not_inhouse():
    assert not is_ampcus_inhouse_candidate(contract_type="FULLTIME")
    assert not is_ampcus_inhouse_candidate(
        organization="Ampcus Inc",
        contract_type="FULLTIME",
    )
    assert not is_ampcus_inhouse_candidate(
        organization="Ampcus Tech Client",
        contract_type="FULLTIME",
    )


def test_resolver_does_not_map_fulltime_to_inhouse():
    r = resolve_candidate_division(
        organization="Ampcus Inc",
        recruiter_work_location="Nashik",
        contract_type="FULLTIME",
    )
    assert r.resolved_division == "nashik"

    r2 = resolve_candidate_division(
        organization="Ampcus Tech",
        recruiter_work_location="Hyderabad",
        contract_type="FULLTIME",
    )
    assert r2.resolved_division == "ampcusTechClient"

    r3 = resolve_candidate_division(
        organization="Ampcus Tech Inhouse",
        recruiter_work_location="Pune",
    )
    assert r3.resolved_division == "ampcusTechInhouse"
