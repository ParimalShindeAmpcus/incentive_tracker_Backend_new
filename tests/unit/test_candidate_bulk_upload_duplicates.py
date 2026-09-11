from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.models.candidates.schemas import CreateVersionRequest, CandidateRowIn
from app.services.candidates import candidate_service
from app.repositories.entities.candidate import Candidate


def _setup_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_bulk_upload_first_import_and_reimport():
    db = _setup_db()

    rows = [
        CandidateRowIn(
            external_candidate_id=f"EXT-{i:03d}",
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
    assert len(res1.duplicates) == 0

    total_cands = db.query(Candidate).count()
    assert total_cands == 20

    # 2. Re-import exact same 20 rows
    req2 = CreateVersionRequest(
        version_label="Import v2",
        source_filename="test_20.csv",
        rows=rows,
    )
    res2 = candidate_service.create_version(db, req2)
    assert res2.created_count == 0
    assert res2.updated_count == 20
    assert res2.duplicate_count == 20
    assert len(res2.duplicates) == 20

    # DB total count must remain 20
    total_cands_after = db.query(Candidate).count()
    assert total_cands_after == 20


def test_bulk_upload_mixed_import():
    db = _setup_db()

    # Seed 10 existing candidates
    initial_rows = [
        CandidateRowIn(
            external_candidate_id=f"EXT-{i:03d}",
            start_id=f"START-{i:03d}",
            activity_id=f"ACT-{i:03d}",
            candidate_name=f"Candidate {i}",
            client="Ampcus Tech",
            start_date=date(2026, 1, 1),
            margin=10,
        )
        for i in range(1, 11)
    ]
    req1 = CreateVersionRequest(
        version_label="Import v1",
        source_filename="initial_10.csv",
        rows=initial_rows,
    )
    candidate_service.create_version(db, req1)
    assert db.query(Candidate).count() == 10

    # Upload mixed: 10 existing (1..10) + 10 new (11..20)
    mixed_rows = [
        CandidateRowIn(
            external_candidate_id=f"EXT-{i:03d}",
            start_id=f"START-{i:03d}",
            activity_id=f"ACT-{i:03d}",
            candidate_name=f"Candidate {i}",
            client="Ampcus Tech",
            start_date=date(2026, 1, 1),
            margin=15,
        )
        for i in range(1, 21)
    ]
    req2 = CreateVersionRequest(
        version_label="Import v2",
        source_filename="mixed_20.csv",
        rows=mixed_rows,
    )
    res2 = candidate_service.create_version(db, req2)
    assert res2.created_count == 10
    assert res2.updated_count == 10
    assert res2.duplicate_count == 10
    assert len(res2.duplicates) == 10
    assert db.query(Candidate).count() == 20


def test_matching_priorities_and_normalization():
    db = _setup_db()

    # Seed candidate with Start ID START-100, Name "John Smith"
    cand1 = CandidateRowIn(
        external_candidate_id="EXT-100",
        start_id="START-100",
        activity_id="ACT-100",
        candidate_name="John Smith",
        client="Ampcus Inc",
    )
    candidate_service.create_version(db, CreateVersionRequest(version_label="v1", rows=[cand1]))
    assert db.query(Candidate).count() == 1

    # 1. Matches by start_id even if name has middle initial
    cand_by_id = CandidateRowIn(
        external_candidate_id="EXT-NEW",
        start_id="START-100",
        candidate_name="John A. Smith",
    )
    res = candidate_service.create_version(db, CreateVersionRequest(version_label="v2", rows=[cand_by_id]))
    assert res.created_count == 0
    assert res.updated_count == 1
    assert db.query(Candidate).count() == 1

    # 2. Matches by normalized name with case and whitespace differences
    cand_by_name = CandidateRowIn(
        external_candidate_id="AUTO-john-smith",
        start_id="N/A",
        activity_id="TBD",
        candidate_name="  JOHN   SMITH  ",
        client="Ampcus Inc",
    )
    res_name = candidate_service.create_version(db, CreateVersionRequest(version_label="v3", rows=[cand_by_name]))
    assert res_name.created_count == 0
    assert res_name.updated_count == 1
    assert db.query(Candidate).count() == 1

    # 3. Genuinely different candidate is newly created
    cand_diff = CandidateRowIn(
        external_candidate_id="EXT-200",
        start_id="START-200",
        candidate_name="Jane Doe",
    )
    res_diff = candidate_service.create_version(db, CreateVersionRequest(version_label="v4", rows=[cand_diff]))
    assert res_diff.created_count == 1
    assert res_diff.updated_count == 0
    assert db.query(Candidate).count() == 2
