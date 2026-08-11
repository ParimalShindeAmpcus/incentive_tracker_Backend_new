from app.services.duplicate_service import (
    find_duplicate_external_ids,
    find_duplicate_name_client,
    paid_dedupe_key,
)


def test_find_duplicate_external_ids():
    rows = [
        {"external_candidate_id": "A1"},
        {"external_candidate_id": "A2"},
        {"external_candidate_id": "A1"},
    ]
    assert find_duplicate_external_ids(rows) == {"a1"}


def test_find_duplicate_name_client():
    rows = [
        {"candidate_name": "Jane Doe", "client": "Acme"},
        {"candidate_name": "Jane  Doe", "client": "Acme"},
    ]
    dupes = find_duplicate_name_client(rows)
    assert len(dupes) == 1


def test_paid_dedupe_key():
    key = paid_dedupe_key(candidate_id=1, role="Recruiter", person="Jane Doe", incentive_type="ONETIME")
    assert "recruiter" in key.lower() or "Recruiter" in key
    assert "1|" in key
