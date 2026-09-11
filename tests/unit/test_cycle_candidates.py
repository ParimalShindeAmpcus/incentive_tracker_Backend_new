from types import SimpleNamespace

from app.services.cycles.cycle_candidates import candidate_matches_division


def candidate(**overrides):
    values = {
        "division": None,
        "organization": None,
        "candidate_source": None,
        "contract_type": "W2",
        "recruiter_location": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_ampcus_client_candidate_matching_normalizes_imported_values():
    assert candidate_matches_division(candidate(organization="AmpcusTech Client"), "ampcusTechClient")
    assert candidate_matches_division(candidate(candidate_source="Ampcus Tech"), "ampcusTechClient")
    assert candidate_matches_division(candidate(division="ampcusTechClient"), "ampcusTechClient")


def test_ampcus_client_candidate_matching_excludes_inhouse():
    assert not candidate_matches_division(
        candidate(organization="Ampcus Tech Inhouse", contract_type="INHOUSE"),
        "ampcusTechClient",
    )
