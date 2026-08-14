from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.repositories.candidates.candidate_repository import create_candidates
from app.repositories.entities.candidate import Candidate, CandidateDataVersion


def test_reimport_updates_start_date_on_existing_candidate():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    v1 = CandidateDataVersion(version_label="v1", division="nashik")
    db.add(v1)
    db.flush()
    cand = Candidate(
        external_candidate_id="12345",
        start_id="12345",
        candidate_name="Aisha Mayes",
        normalized_name="aisha mayes",
        division="nashik",
        source_version_id=v1.id,
        last_touched_version_id=v1.id,
        start_date=None,
        incentive_active=True,
        is_active=True,
    )
    db.add(cand)
    db.flush()
    v2 = CandidateDataVersion(version_label="v2", division="nashik")
    db.add(v2)
    db.flush()
    create_candidates(
        db,
        v2,
        [
            {
                "external_candidate_id": "12345",
                "start_id": "12345",
                "candidate_name": "Aisha Mayes",
                "start_date": date(2026, 1, 1),
                "contract_type": "C2C",
                "margin": 12,
            }
        ],
    )
    db.refresh(cand)
    assert cand.start_date == date(2026, 1, 1)
    assert cand.contract_type == "C2C"
