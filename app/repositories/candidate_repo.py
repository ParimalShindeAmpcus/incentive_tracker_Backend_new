from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.candidate import Candidate, CandidateDataVersion


def create_version(db: Session, **kwargs) -> CandidateDataVersion:
    row = CandidateDataVersion(**kwargs)
    db.add(row)
    db.flush()
    return row


def get_version(db: Session, version_id: int) -> Optional[CandidateDataVersion]:
    return db.query(CandidateDataVersion).filter(CandidateDataVersion.id == version_id).first()


def list_versions(db: Session, *, offset: int = 0, limit: int = 50) -> List[CandidateDataVersion]:
    return (
        db.query(CandidateDataVersion)
        .order_by(CandidateDataVersion.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def count_versions(db: Session) -> int:
    return db.query(CandidateDataVersion).count()


def get_candidate(db: Session, candidate_id: int) -> Optional[Candidate]:
    return db.query(Candidate).filter(Candidate.id == candidate_id).first()


def get_by_external_id(
    db: Session, external_candidate_id: str, *, division: Optional[str] = None
) -> Optional[Candidate]:
    q = db.query(Candidate).filter(Candidate.external_candidate_id == external_candidate_id)
    if division:
        q = q.filter(Candidate.division == division)
    return q.first()


def get_by_start_id(db: Session, start_id: str) -> Optional[Candidate]:
    return db.query(Candidate).filter(Candidate.start_id == start_id).first()


def find_by_normalized_name_client(
    db: Session, normalized_name: str, normalized_client: Optional[str] = None
) -> List[Candidate]:
    q = db.query(Candidate).filter(Candidate.normalized_name == normalized_name)
    if normalized_client:
        q = q.filter(Candidate.normalized_client == normalized_client)
    return q.all()


def list_candidates(
    db: Session,
    *,
    division: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
) -> List[Candidate]:
    q = db.query(Candidate).order_by(Candidate.id.desc())
    if division:
        q = q.filter(Candidate.division == division)
    return q.offset(offset).limit(limit).all()


def count_candidates(db: Session, *, division: Optional[str] = None) -> int:
    q = db.query(Candidate)
    if division:
        q = q.filter(Candidate.division == division)
    return q.count()


def create_candidate(db: Session, **kwargs) -> Candidate:
    row = Candidate(**kwargs)
    db.add(row)
    db.flush()
    return row


def update_candidate(db: Session, candidate: Candidate, **kwargs) -> Candidate:
    for k, v in kwargs.items():
        setattr(candidate, k, v)
    db.flush()
    return candidate


def all_for_matching(db: Session, *, division: Optional[str] = None) -> List[Candidate]:
    q = db.query(Candidate).filter(Candidate.is_active.is_(True))
    if division:
        q = q.filter(Candidate.division == division)
    return q.all()
