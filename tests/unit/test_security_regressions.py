from app.core.db import get_db
from app.repositories.entities.vlookup import VLookupMatchedRecord


def test_protected_routes_require_auth(client):
    response = client.get("/api/v1/candidates")
    assert response.status_code == 401, response.text


def test_vlookup_accept_rejects_client_reviewed_by_spoof(client):
    session_factory = client.app.dependency_overrides[get_db]
    seed_db = next(session_factory())
    match = VLookupMatchedRecord(
        template_candidate_id=1,
        template_candidate_name="Alice Sample",
        messy_name_original="Alice Sample",
        messy_month="2026-09",
        total_hours=80,
        confidence_score=0.9,
        match_status="needs_review",
        match_method="manual",
        upload_batch_id="batch-spoof-test",
    )
    seed_db.add(match)
    seed_db.commit()
    seed_db.refresh(match)
    seed_db.close()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "Admin@123"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    response = client.post(
        f"/api/v1/vlookup/matches/{match.id}/accept",
        json={"reviewed_by": "attacker@evil.test", "notes": "spoof test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text

    verify_db = next(session_factory())
    refreshed = verify_db.query(VLookupMatchedRecord).filter_by(id=match.id).one()
    assert refreshed.reviewed_by == "admin@example.com"
    assert refreshed.review_action == "accepted"
    verify_db.close()
