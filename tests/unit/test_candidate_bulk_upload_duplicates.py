"""Option A strict zero-fallback Candidate deduplication and update vs duplicate tests.

Tests validate:
1. Name-only rejection (no valid Start ID or Activity ID)
2. Same name, different Start IDs → 2 distinct Candidates
3. Cross-field collision prevention (start_id ≠ activity_id field)
4. Activity ID fallback when Start ID is missing
5. Placeholder ID rejection (N/A, --, etc.)
6. External ID only rejection
7. In-file duplicate handling
8. Pure Source-of-Truth — No financial derivations (margin, markup)
9. Pure Source-of-Truth — No ownership inference from recruiter presence
10. Pure Source-of-Truth — No cross-copying of fees and rates
11. Pure Source-of-Truth — Past end_date does not mutate status or active
12. Existing candidate updated with new data
13. Field clearing contract — Blank clears, omitted preserves
14. Candidate name non-clearable rule — Blank cell does not erase name
15. candidate_service.create_version end-to-end with exclude_unset=True
16. Re-uploading exact same rows reports DUPLICATE (0 updated, 20 duplicate)
17. Partial update reports distinct updated and duplicate counts (e.g., 2 updated, 8 duplicate)
18. Mixed bulk upload counts (3 new, 2 updated, 4 duplicate, 1 rejected)
19. Numeric equality normalization (50.0 == 50.0000) prevents false updates
20. Whitespace stripped string comparison prevents false updates
21. Blank candidate name preserves name and counts as DUPLICATE if other fields unchanged
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.repositories.candidates.candidate_repository import (
    create_candidates,
    _is_placeholder_id,
    _clean_id,
    values_differ,
)
from app.repositories.entities.candidate import Candidate, CandidateDataVersion


def _setup_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _make_version(db, label="v1"):
    v = CandidateDataVersion(version_label=label, division="test")
    db.add(v)
    db.flush()
    return v


# ---------------------------------------------------------------------------
# Test 1: Name only (no valid Start ID or Activity ID) → REJECTED
# ---------------------------------------------------------------------------
def test_name_only_rejected():
    db = _setup_db()
    v = _make_version(db)

    new, updated, duplicates, rejected = create_candidates(db, v, [
        {"candidate_name": "John Smith"},
    ])

    assert len(new) == 0
    assert len(updated) == 0
    assert len(duplicates) == 0
    assert len(rejected) == 1
    assert rejected[0]["status"] == "REJECTED"
    assert "Missing valid Start ID or Activity ID" in rejected[0]["reason"]
    assert db.query(Candidate).count() == 0


# ---------------------------------------------------------------------------
# Test 2: Same name, different Start IDs → 2 Candidates
# ---------------------------------------------------------------------------
def test_same_name_different_start_ids_creates_two():
    db = _setup_db()
    v = _make_version(db)

    new, updated, duplicates, rejected = create_candidates(db, v, [
        {"candidate_name": "John Smith", "start_id": "1001"},
        {"candidate_name": "John Smith", "start_id": "1002"},
    ])

    assert len(new) == 2
    assert len(updated) == 0
    assert len(duplicates) == 0
    assert len(rejected) == 0
    assert db.query(Candidate).count() == 2


# ---------------------------------------------------------------------------
# Test 3: Cross-field collision (existing start_id = 1001, incoming activity_id = 1001) → NO MATCH
# ---------------------------------------------------------------------------
def test_cross_field_collision_no_match():
    db = _setup_db()
    v1 = _make_version(db, "v1")

    # Seed candidate with start_id = "1001"
    new1, _, _, _ = create_candidates(db, v1, [
        {"candidate_name": "Alice", "start_id": "1001", "activity_id": "ACT-999"},
    ])
    assert len(new1) == 1
    assert db.query(Candidate).count() == 1

    # Incoming row with activity_id = "1001" (no valid start_id)
    # This MUST NOT match the existing candidate whose start_id = "1001"
    v2 = _make_version(db, "v2")
    new2, updated2, duplicates2, rejected2 = create_candidates(db, v2, [
        {"candidate_name": "Bob", "activity_id": "1001"},
    ])

    assert len(new2) == 1, "Should create a NEW candidate, not match the existing one"
    assert len(updated2) == 0
    assert len(duplicates2) == 0
    assert len(rejected2) == 0
    assert db.query(Candidate).count() == 2


# ---------------------------------------------------------------------------
# Test 4: Activity ID fallback (existing activity_id = ACT-500, incoming has no start_id) → UPDATE
# ---------------------------------------------------------------------------
def test_activity_id_fallback_updates_existing():
    db = _setup_db()
    v1 = _make_version(db, "v1")

    new1, _, _, _ = create_candidates(db, v1, [
        {"candidate_name": "Charlie", "activity_id": "ACT-500"},
    ])
    assert len(new1) == 1
    assert db.query(Candidate).count() == 1

    # Re-import with same activity_id, no start_id
    v2 = _make_version(db, "v2")
    new2, updated2, duplicates2, rejected2 = create_candidates(db, v2, [
        {"candidate_name": "Charlie Updated", "activity_id": "ACT-500"},
    ])

    assert len(new2) == 0
    assert len(updated2) == 1, "Should UPDATE the existing candidate by activity_id"
    assert len(duplicates2) == 0
    assert len(rejected2) == 0
    assert db.query(Candidate).count() == 1


# ---------------------------------------------------------------------------
# Test 5: Placeholder IDs (start_id = N/A, activity_id = --) → REJECTED
# ---------------------------------------------------------------------------
def test_placeholder_ids_rejected():
    db = _setup_db()
    v = _make_version(db)

    new, updated, duplicates, rejected = create_candidates(db, v, [
        {"candidate_name": "Dave", "start_id": "N/A", "activity_id": "--"},
    ])

    assert len(new) == 0
    assert len(updated) == 0
    assert len(duplicates) == 0
    assert len(rejected) == 1
    assert rejected[0]["status"] == "REJECTED"
    assert db.query(Candidate).count() == 0

    # Also verify the placeholder helper itself
    assert _is_placeholder_id("N/A") is True
    assert _is_placeholder_id("--") is True
    assert _is_placeholder_id("---") is True
    assert _is_placeholder_id("TBD") is True
    assert _is_placeholder_id("pending") is True
    assert _is_placeholder_id("0") is True
    assert _is_placeholder_id("none") is True
    assert _is_placeholder_id("unknown") is True
    assert _is_placeholder_id("null") is True
    assert _is_placeholder_id("nil") is True
    assert _is_placeholder_id("blank") is True
    assert _is_placeholder_id("n.a.") is True
    assert _is_placeholder_id("notapplicable") is True
    assert _is_placeholder_id("auto-123") is True
    assert _is_placeholder_id("cand-456") is True
    assert _is_placeholder_id("START-100") is False
    assert _is_placeholder_id("ACT-500") is False


# ---------------------------------------------------------------------------
# Test 6: External ID only (no start_id, no activity_id) → REJECTED
# ---------------------------------------------------------------------------
def test_external_id_only_rejected():
    db = _setup_db()
    v = _make_version(db)

    new, updated, duplicates, rejected = create_candidates(db, v, [
        {"candidate_name": "Eve", "external_candidate_id": "EXT-500"},
    ])

    assert len(new) == 0
    assert len(updated) == 0
    assert len(duplicates) == 0
    assert len(rejected) == 1
    assert rejected[0]["status"] == "REJECTED"
    assert db.query(Candidate).count() == 0


# ---------------------------------------------------------------------------
# Test 7: In-file duplicate handled (same Start ID in two rows)
# ---------------------------------------------------------------------------
def test_in_file_duplicate_handled():
    db = _setup_db()
    v = _make_version(db)

    # First row creates, second row with new field updates
    new, updated, duplicates, rejected = create_candidates(db, v, [
        {"candidate_name": "Frank", "start_id": "1001"},
        {"candidate_name": "Frank", "start_id": "1001", "job_title": "Developer"},
    ])

    assert len(new) == 1, "First occurrence creates the candidate"
    assert len(updated) == 1, "Second occurrence updates the same candidate"
    assert len(duplicates) == 0
    assert len(rejected) == 0
    assert db.query(Candidate).count() == 1

    # Two exact identical rows in same file
    v2 = _make_version(db, "v2")
    new2, updated2, duplicates2, rejected2 = create_candidates(db, v2, [
        {"candidate_name": "George", "start_id": "1002"},
        {"candidate_name": "George", "start_id": "1002"},
    ])
    assert len(new2) == 1
    assert len(updated2) == 0
    assert len(duplicates2) == 1
    assert len(rejected2) == 0


# ---------------------------------------------------------------------------
# Test: Excel float normalization (1001.0 → 1001)
# ---------------------------------------------------------------------------
def test_clean_id_normalizes_excel_floats():
    assert _clean_id("1001.0") == "1001"
    assert _clean_id("1001") == "1001"
    assert _clean_id(" 1001.0 ") == "1001"
    assert _clean_id("ACT-500") == "ACT-500"
    assert _clean_id(None) == ""
    assert _clean_id("") == ""


# ---------------------------------------------------------------------------
# Test: First import and reimport via service (end-to-end) — DUPLICATE NOT UPDATED
# ---------------------------------------------------------------------------
def test_bulk_upload_first_import_and_reimport():
    from app.models.candidates.schemas import CreateVersionRequest, CandidateRowIn
    from app.services.candidates import candidate_service

    db = _setup_db()

    rows = [
        CandidateRowIn(
            start_id=f"START-{i:03d}",
            activity_id=f"ACT-{i:03d}",
            candidate_name=f"Candidate {i}",
            client="Ampcus Tech",
            start_date=date(2026, 1, 1),
            contract_type="W2",
            margin=10,
        )
        for i in range(1, 21)
    ]

    # 1. First import: 20 rows
    req1 = CreateVersionRequest(
        version_label="Import v1",
        source_filename="test_20.csv",
        rows=rows,
    )
    res1 = candidate_service.create_version(db, req1)
    assert res1.created_count == 20
    assert res1.updated_count == 0
    assert res1.duplicate_count == 0
    assert res1.rejected_count == 0

    total_cands = db.query(Candidate).count()
    assert total_cands == 20

    # 2. Re-import exact same 20 rows -> MUST BE 20 DUPLICATES, 0 UPDATED
    req2 = CreateVersionRequest(
        version_label="Import v2",
        source_filename="test_20.csv",
        rows=rows,
    )
    res2 = candidate_service.create_version(db, req2)
    assert res2.created_count == 0
    assert res2.updated_count == 0
    assert res2.duplicate_count == 20
    assert res2.rejected_count == 0
    assert all(d.status == "DUPLICATE" for d in res2.duplicates)

    # DB total count must remain 20
    total_cands_after = db.query(Candidate).count()
    assert total_cands_after == 20


# ---------------------------------------------------------------------------
# Test 8: Pure Source-of-Truth — No financial derivations (margin, markup)
# ---------------------------------------------------------------------------
def test_pure_source_of_truth_no_financial_derivations():
    db = _setup_db()
    v = _make_version(db)

    # Row has bill_rate and pay_rate, but NO margin and NO markup_percent
    new, updated, duplicates, rejected = create_candidates(db, v, [
        {
            "candidate_name": "Grace",
            "start_id": "START-801",
            "bill_rate": 50.0,
            "pay_rate": 35.0,
        },
    ])

    assert len(new) == 1
    cand = new[0]
    # Margin and markup must remain None — NOT derived as 50 - 35 or (15/35)*100
    assert cand.margin is None
    assert cand.markup_percent is None
    assert cand.approved_markup_percentage is None


# ---------------------------------------------------------------------------
# Test 9: Pure Source-of-Truth — No ownership inference from recruiter presence
# ---------------------------------------------------------------------------
def test_pure_source_of_truth_no_ownership_inference():
    db = _setup_db()
    v = _make_version(db)

    new, updated, duplicates, rejected = create_candidates(db, v, [
        {
            "candidate_name": "Hank",
            "start_id": "START-802",
            "recruiter": "Jane Recruiter",
        },
    ])

    assert len(new) == 1
    cand = new[0]
    # Ownership confirmed must NOT be inferred merely because recruiter is present
    assert cand.ownership_confirmed is False


# ---------------------------------------------------------------------------
# Test 10: Pure Source-of-Truth — No cross-copying of fees and rates
# ---------------------------------------------------------------------------
def test_pure_source_of_truth_no_fee_cross_copying():
    db = _setup_db()
    v = _make_version(db)

    new, updated, duplicates, rejected = create_candidates(db, v, [
        {
            "candidate_name": "Ian",
            "start_id": "START-803",
            "referral_fee": 500.0,
            # finders_fee omitted
        },
    ])

    assert len(new) == 1
    cand = new[0]
    assert float(cand.referral_fee) == 500.0
    assert cand.finders_fee is None, "referral_fee must NOT be copied into finders_fee"


# ---------------------------------------------------------------------------
# Test 11: Pure Source-of-Truth — Past end_date does not mutate status or active
# ---------------------------------------------------------------------------
def test_pure_source_of_truth_no_date_based_status_mutation():
    db = _setup_db()
    v = _make_version(db)

    new, updated, duplicates, rejected = create_candidates(db, v, [
        {
            "candidate_name": "Judy",
            "start_id": "START-804",
            "end_date": date(2020, 1, 1),  # In the past
            "status": "Active",
            "incentive_active": True,
        },
    ])

    assert len(new) == 1
    cand = new[0]
    assert cand.status == "Active", "Past end_date must NOT overwrite status to Inactive (Excluded)"
    assert cand.incentive_active is True, "Past end_date must NOT flip incentive_active to False"
    assert cand.inactivation_reason is None, "Must NOT manufacture an inactivation reason"


# ---------------------------------------------------------------------------
# Test 12: Existing candidate updated with new data (Name, Title, Pay Rate, Client)
# ---------------------------------------------------------------------------
def test_existing_candidate_updated_with_new_data():
    db = _setup_db()
    v1 = _make_version(db, "v1")

    # Initial import: ID 101, Junior Dev, Rate 30, ABC
    new1, updated1, duplicates1, rejected1 = create_candidates(db, v1, [
        {
            "start_id": "101",
            "candidate_name": "Original Name",
            "job_title": "Junior Dev",
            "pay_rate": 30.0,
            "client": "ABC",
        }
    ])
    assert len(new1) == 1
    assert len(updated1) == 0

    # Second import: ID 101, Updated Name, Senior Dev, Rate 55, XYZ
    v2 = _make_version(db, "v2")
    new2, updated2, duplicates2, rejected2 = create_candidates(db, v2, [
        {
            "start_id": "101",
            "candidate_name": "Updated Name",
            "job_title": "Senior Dev",
            "pay_rate": 55.0,
            "client": "XYZ",
        }
    ])
    assert len(new2) == 0
    assert len(updated2) == 1
    assert len(duplicates2) == 0
    assert len(rejected2) == 0

    cand = db.query(Candidate).filter(Candidate.start_id == "101").one()
    assert cand.candidate_name == "Updated Name"
    assert cand.normalized_name == "updated name"
    assert cand.job_title == "Senior Dev"
    assert float(cand.pay_rate) == 55.0
    assert cand.client == "XYZ"
    assert cand.normalized_client == "xyz"
    assert cand.last_touched_version_id == v2.id


# ---------------------------------------------------------------------------
# Test 13: Field clearing contract — Blank clears, omitted preserves
# ---------------------------------------------------------------------------
def test_field_clearing_vs_omitted_column_preservation():
    db = _setup_db()
    v1 = _make_version(db, "v1")

    new1, _, _, _ = create_candidates(db, v1, [
        {
            "start_id": "102",
            "candidate_name": "Rahul Sharma",
            "email": "rahul@gmail.com",
            "job_title": "Senior Developer",
            "contact": "1234567890",
        }
    ])
    assert len(new1) == 1

    v2 = _make_version(db, "v2")
    # In v2 payload: email is explicitly blank (None), job_title is omitted, contact is updated
    new2, updated2, duplicates2, rejected2 = create_candidates(db, v2, [
        {
            "start_id": "102",
            "email": None,  # Explicit blank -> should clear
            # job_title is omitted -> should be preserved
            "contact": "9876543210",  # Updated value
        }
    ])
    assert len(new2) == 0
    assert len(updated2) == 1
    assert len(duplicates2) == 0

    cand = db.query(Candidate).filter(Candidate.start_id == "102").one()
    assert cand.email is None, "Email should be cleared to NULL because it was supplied as blank"
    assert cand.job_title == "Senior Developer", "Job title should be preserved because column was omitted"
    assert cand.contact == "9876543210", "Contact should be updated with new value"
    assert cand.candidate_name == "Rahul Sharma", "Name should be preserved when omitted"


# ---------------------------------------------------------------------------
# Test 14: Candidate name non-clearable rule — Blank cell does not erase name
# ---------------------------------------------------------------------------
def test_candidate_name_blank_does_not_clear_existing_name():
    db = _setup_db()
    v1 = _make_version(db, "v1")

    new1, _, _, _ = create_candidates(db, v1, [
        {
            "start_id": "103",
            "candidate_name": "Rahul Sharma",
            "job_title": "Engineer",
        }
    ])
    assert len(new1) == 1

    v2 = _make_version(db, "v2")
    # In v2: candidate_name is empty string or None, job_title updated
    new2, updated2, duplicates2, rejected2 = create_candidates(db, v2, [
        {
            "start_id": "103",
            "candidate_name": "",  # Empty string
            "job_title": "Lead Engineer",
        }
    ])
    assert len(new2) == 0
    assert len(updated2) == 1
    assert len(duplicates2) == 0

    cand = db.query(Candidate).filter(Candidate.start_id == "103").one()
    assert cand.candidate_name == "Rahul Sharma", "Blank candidate name must NOT erase existing name"
    assert cand.job_title == "Lead Engineer", "Job title should be updated"


# ---------------------------------------------------------------------------
# Test 15: candidate_service.create_version end-to-end with exclude_unset=True
# ---------------------------------------------------------------------------
def test_candidate_service_create_version_exclude_unset():
    from app.services.candidates import candidate_service
    from app.models.candidates.schemas import CreateVersionRequest, CandidateRowIn

    db = _setup_db()

    # Step 1: Create initial candidate with full info
    req1 = CreateVersionRequest(
        version_label="v1",
        rows=[
            CandidateRowIn(
                start_id="105",
                candidate_name="Alice Brown",
                email="alice@brown.com",
                job_title="Designer",
                pay_rate=40.0,
            )
        ]
    )
    res1 = candidate_service.create_version(db, req1)
    assert res1.created_count == 1
    assert res1.updated_count == 0
    assert res1.duplicate_count == 0

    # Step 2: Upload v2 with only start_id, job_title, and email=None (unset fields omitted)
    req2 = CreateVersionRequest(
        version_label="v2",
        rows=[
            CandidateRowIn.model_validate({
                "start_id": "105",
                "job_title": "Senior Designer",
                "email": None,  # Explicit blank
                # pay_rate is unset / omitted!
            })
        ]
    )
    res2 = candidate_service.create_version(db, req2)
    assert res2.created_count == 0
    assert res2.updated_count == 1
    assert res2.duplicate_count == 0
    assert res2.duplicates[0].status == "UPDATED"
    assert "updated 2 field(s)" in res2.duplicates[0].reason

    cand = db.query(Candidate).filter(Candidate.start_id == "105").one()
    assert cand.candidate_name == "Alice Brown", "Name preserved"
    assert cand.job_title == "Senior Designer", "Title updated"
    assert cand.email is None, "Email cleared"
    assert float(cand.pay_rate) == 40.0, "Pay rate preserved because it was omitted from payload"


# ---------------------------------------------------------------------------
# Test 16: Partial update reports distinct updated and duplicate counts (2 updated, 8 duplicate)
# ---------------------------------------------------------------------------
def test_partial_update_reports_distinct_updated_and_duplicate_counts():
    from app.services.candidates import candidate_service
    from app.models.candidates.schemas import CreateVersionRequest, CandidateRowIn

    db = _setup_db()

    initial_rows = [
        CandidateRowIn(
            start_id=f"ST-{i}",
            candidate_name=f"Candidate {i}",
            job_title="Engineer",
            pay_rate=50.0,
        )
        for i in range(1, 11)
    ]

    # Initial upload: 10 created
    res1 = candidate_service.create_version(db, CreateVersionRequest(version_label="v1", rows=initial_rows))
    assert res1.created_count == 10
    assert res1.updated_count == 0
    assert res1.duplicate_count == 0

    # Upload again: modify only candidates 3 and 7 (e.g., job title and pay rate)
    second_rows = [
        CandidateRowIn(
            start_id=f"ST-{i}",
            candidate_name=f"Candidate {i}",
            job_title="Lead Engineer" if i in (3, 7) else "Engineer",
            pay_rate=65.0 if i == 3 else 50.0,
        )
        for i in range(1, 11)
    ]

    res2 = candidate_service.create_version(db, CreateVersionRequest(version_label="v2", rows=second_rows))
    assert res2.created_count == 0
    assert res2.updated_count == 2
    assert res2.duplicate_count == 8
    assert res2.rejected_count == 0

    # Verify duplicate details
    updated_items = [d for d in res2.duplicates if d.status == "UPDATED"]
    duplicate_items = [d for d in res2.duplicates if d.status == "DUPLICATE"]
    assert len(updated_items) == 2
    assert len(duplicate_items) == 8

    # Verify changed fields
    cand3_info = next(d for d in updated_items if d.start_id == "ST-3")
    assert set(cand3_info.changed_fields) == {"job_title", "pay_rate"}
    cand7_info = next(d for d in updated_items if d.start_id == "ST-7")
    assert set(cand7_info.changed_fields) == {"job_title"}


# ---------------------------------------------------------------------------
# Test 17: Mixed bulk upload counts (3 new, 2 updated, 4 duplicate, 1 rejected)
# ---------------------------------------------------------------------------
def test_mixed_bulk_upload_counts():
    from app.services.candidates import candidate_service
    from app.models.candidates.schemas import CreateVersionRequest, CandidateRowIn

    db = _setup_db()

    # Initial DB has 6 candidates: ST-1 to ST-6
    init_rows = [
        CandidateRowIn(start_id=f"ST-{i}", candidate_name=f"User {i}", client="Client A")
        for i in range(1, 7)
    ]
    candidate_service.create_version(db, CreateVersionRequest(version_label="v1", rows=init_rows))

    # Next upload has 10 rows:
    # 4 duplicate (ST-1, ST-2, ST-3, ST-4 unchanged)
    # 2 updated (ST-5 client changed, ST-6 client changed)
    # 3 new (ST-7, ST-8, ST-9)
    # 1 rejected (no start_id, no activity_id)
    mixed_payload_rows = [
        # 4 duplicates
        CandidateRowIn(start_id="ST-1", candidate_name="User 1", client="Client A"),
        CandidateRowIn(start_id="ST-2", candidate_name="User 2", client="Client A"),
        CandidateRowIn(start_id="ST-3", candidate_name="User 3", client="Client A"),
        CandidateRowIn(start_id="ST-4", candidate_name="User 4", client="Client A"),
        # 2 updated
        CandidateRowIn(start_id="ST-5", candidate_name="User 5", client="Client B"),
        CandidateRowIn(start_id="ST-6", candidate_name="User 6", client="Client C"),
        # 3 new
        CandidateRowIn(start_id="ST-7", candidate_name="User 7", client="Client A"),
        CandidateRowIn(start_id="ST-8", candidate_name="User 8", client="Client A"),
        CandidateRowIn(start_id="ST-9", candidate_name="User 9", client="Client A"),
        # 1 rejected
        CandidateRowIn(candidate_name="No ID User"),
    ]

    res = candidate_service.create_version(
        db, CreateVersionRequest(version_label="v2", rows=mixed_payload_rows)
    )

    assert res.created_count == 3
    assert res.updated_count == 2
    assert res.duplicate_count == 4
    assert res.rejected_count == 1
    assert len(res.rejected_rows) == 1
    assert res.rejected_rows[0]["status"] == "REJECTED"


# ---------------------------------------------------------------------------
# Test 18: Numeric equality normalization prevents false updates
# ---------------------------------------------------------------------------
def test_numeric_equality_prevents_false_updates():
    db = _setup_db()
    v1 = _make_version(db, "v1")

    # Stored with pay_rate = 50.00
    create_candidates(db, v1, [
        {"start_id": "NUM-1", "candidate_name": "Num User", "pay_rate": 50.0}
    ])

    v2 = _make_version(db, "v2")
    # Incoming row has pay_rate = Decimal("50.0000") or float 50.0
    new, updated, duplicates, rejected = create_candidates(db, v2, [
        {"start_id": "NUM-1", "candidate_name": "Num User", "pay_rate": Decimal("50.0000")}
    ])

    assert len(new) == 0
    assert len(updated) == 0, "Mathematically identical decimal must NOT trigger update"
    assert len(duplicates) == 1
    assert len(rejected) == 0


# ---------------------------------------------------------------------------
# Test 19: Whitespace stripped string comparison prevents false updates
# ---------------------------------------------------------------------------
def test_whitespace_stripped_string_prevents_false_updates():
    db = _setup_db()
    v1 = _make_version(db, "v1")

    create_candidates(db, v1, [
        {"start_id": "STR-1", "candidate_name": "Str User", "job_title": "Developer"}
    ])

    v2 = _make_version(db, "v2")
    # Incoming with trailing and leading whitespace
    new, updated, duplicates, rejected = create_candidates(db, v2, [
        {"start_id": "STR-1", "candidate_name": "Str User", "job_title": "  Developer  "}
    ])

    assert len(new) == 0
    assert len(updated) == 0, "Whitespace-only difference in string must NOT trigger update"
    assert len(duplicates) == 1
    assert len(rejected) == 0


# ---------------------------------------------------------------------------
# Test 20: Blank candidate name preserves name and counts as DUPLICATE if other fields unchanged
# ---------------------------------------------------------------------------
def test_blank_candidate_name_counts_as_duplicate_if_other_fields_unchanged():
    db = _setup_db()
    v1 = _make_version(db, "v1")

    create_candidates(db, v1, [
        {"start_id": "NAME-1", "candidate_name": "Permanent Name", "job_title": "Analyst"}
    ])

    v2 = _make_version(db, "v2")
    # Incoming has empty candidate name and identical job_title
    new, updated, duplicates, rejected = create_candidates(db, v2, [
        {"start_id": "NAME-1", "candidate_name": "", "job_title": "Analyst"}
    ])

    assert len(new) == 0
    assert len(updated) == 0, "Blank candidate name cannot clear name; if nothing else changed, it is DUPLICATE"
    assert len(duplicates) == 1
    cand = db.query(Candidate).filter(Candidate.start_id == "NAME-1").one()
    assert cand.candidate_name == "Permanent Name"


# ---------------------------------------------------------------------------
# Test 21: Unit tests for values_differ helper function
# ---------------------------------------------------------------------------
def test_values_differ_cases():
    # String
    assert values_differ("Developer", "Developer", "job_title") is False
    assert values_differ("Developer", " Developer ", "job_title") is False
    assert values_differ("Developer", "Senior Developer", "job_title") is True
    assert values_differ(None, "", "job_title") is False
    assert values_differ("", None, "job_title") is False
    assert values_differ("Dev", "", "job_title") is True
    assert values_differ(None, "Dev", "job_title") is True

    # Numeric
    assert values_differ(Decimal("50.00"), Decimal("50"), "pay_rate") is False
    assert values_differ(Decimal("50.00"), 50.0, "pay_rate") is False
    assert values_differ(50.0, Decimal("50.0000"), "pay_rate") is False
    assert values_differ(50.0, 55.0, "pay_rate") is True
    assert values_differ(None, 50.0, "pay_rate") is True
    assert values_differ(50.0, None, "pay_rate") is True
    assert values_differ(None, None, "pay_rate") is False

    # Date
    assert values_differ(date(2026, 1, 1), date(2026, 1, 1), "start_date") is False
    assert values_differ(date(2026, 1, 1), date(2026, 2, 1), "start_date") is True
    assert values_differ(date(2026, 1, 1), "2026-01-01", "start_date") is False
    assert values_differ(date(2026, 1, 1), None, "start_date") is True
    assert values_differ(None, date(2026, 1, 1), "start_date") is True

    # Boolean
    assert values_differ(True, True, "ownership_confirmed") is False
    assert values_differ(True, False, "ownership_confirmed") is True
    assert values_differ(False, 0, "ownership_confirmed") is False
    assert values_differ(True, 1, "ownership_confirmed") is False
