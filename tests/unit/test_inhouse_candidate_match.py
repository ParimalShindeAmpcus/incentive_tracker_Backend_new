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


def test_inhouse_client_and_end_client_matching():
    # Client has Ampcus Tech In-House
    assert is_ampcus_inhouse_candidate(client="Ampcus Tech In-House")
    assert is_ampcus_inhouse_candidate(client="ampcustech-inhouse")
    assert is_ampcus_inhouse_candidate(organization="Ampcustech", client="Ampcus Tech In-House")

    # End client has Ampcus Tech Internal
    assert is_ampcus_inhouse_candidate(end_client="Ampcus Tech Internal")
    assert is_ampcus_inhouse_candidate(organization="Ampcustech", end_client="Ampcus Tech Internal")

    # Organization has Ampcus Tech In-House / Ampcusinhouse
    assert is_ampcus_inhouse_candidate(organization="Ampcus Tech In-House")
    assert is_ampcus_inhouse_candidate(organization="Ampcusinhouse")

    # Non in-house with Nashik location does NOT match
    assert not is_ampcus_inhouse_candidate(
        organization="Ampcus Inc",
        client="Persistent Systems",
        end_client="Contoso Energy",
    )


def test_inhouse_candidate_object_matching():
    class MockCand:
        def __init__(self, org=None, client=None, end_client=None, loc=None):
            self.organization = org
            self.client = client
            self.end_client = end_client
            self.recruiter_location = loc
            self.work_location = loc

    # Even with Nashik location, inhouse client qualifies
    c1 = MockCand(org="Ampcustech", client="Ampcus Tech In-House", loc="Nashik")
    assert is_ampcus_inhouse_candidate(c1)

    # External client with Nashik location does NOT qualify
    c2 = MockCand(org="Ampcus Inc", client="Persistent Systems", loc="Nashik")
    assert not is_ampcus_inhouse_candidate(c2)


def test_inhouse_does_not_match_nashik_division():
    from app.services.cycles.cycle_candidates import candidate_matches_division

    class MockCand:
        def __init__(self, name, org, client, end_client, rec_loc, work_loc):
            self.candidate_name = name
            self.organization = org
            self.client = client
            self.end_client = end_client
            self.recruiter_location = rec_loc
            self.work_location = work_loc
            self.candidate_source = None
            self.division = None
            self.contract_type = "FULLTIME"

    # Anita Desai: In-House employee sitting in Nashik Office
    anita = MockCand(
        name="Anita Desai",
        org="Ampcus Tech In-House",
        client="Ampcus Tech In-House",
        end_client="Ampcus Tech Internal",
        rec_loc=None,
        work_loc="Nashik Office",
    )
    assert candidate_matches_division(anita, "ampcusTechInhouse") is True
    assert candidate_matches_division(anita, "nashik") is False

    # Kavya Pillai: External Nashik employee
    kavya = MockCand(
        name="Kavya Pillai",
        org="Ampcus Inc",
        client="Acme CORP",
        end_client="Acme Corp",
        rec_loc="Nashik",
        work_loc="Remote",
    )
    assert candidate_matches_division(kavya, "ampcusTechInhouse") is False
    assert candidate_matches_division(kavya, "nashik") is True


