"""Candidate repository — SQL only."""

from typing import List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.repositories.entities.candidate import Candidate, CandidateDataVersion


def list_candidates(
    db: Session,
    *,
    division: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> Tuple[List[Candidate], int]:
    q = db.query(Candidate)
    if division:
        q = q.filter(Candidate.division == division)
    total = q.count()
    rows = q.order_by(Candidate.id).offset(skip).limit(limit).all()
    return rows, total


def get_candidate(db: Session, candidate_id: int) -> Optional[Candidate]:
    return db.query(Candidate).filter(Candidate.id == candidate_id).first()


def get_candidate_by_external_id(db: Session, external_candidate_id: str) -> Optional[Candidate]:
    return (
        db.query(Candidate)
        .filter(Candidate.external_candidate_id == external_candidate_id)
        .order_by(Candidate.id.desc())
        .first()
    )


def update_candidate(db: Session, candidate: Candidate, data: dict) -> Candidate:
    for key, value in data.items():
        if value is not None or key in data:
            setattr(candidate, key, value)
    db.add(candidate)
    db.flush()
    return candidate


def list_versions(db: Session, division: Optional[str] = None) -> List[CandidateDataVersion]:
    q = db.query(CandidateDataVersion)
    if division:
        q = q.filter(CandidateDataVersion.division == division)
    return q.order_by(CandidateDataVersion.id.desc()).all()


def get_version(db: Session, version_id: int) -> Optional[CandidateDataVersion]:
    return db.query(CandidateDataVersion).filter(CandidateDataVersion.id == version_id).first()


def create_version(
    db: Session,
    *,
    version_label: str,
    division: Optional[str] = None,
    source_filename: Optional[str] = None,
    notes: Optional[str] = None,
    uploaded_by: Optional[int] = None,
    row_count: int = 0,
) -> CandidateDataVersion:
    version = CandidateDataVersion(
        version_label=version_label,
        division=division,
        source_filename=source_filename,
        notes=notes,
        uploaded_by=uploaded_by,
        row_count=row_count,
    )
    db.add(version)
    db.flush()
    return version


def create_candidates(
    db: Session,
    version: CandidateDataVersion,
    rows: Sequence[dict],
) -> List[Candidate]:
    created: List[Candidate] = []
    for row in rows:
        name = row["candidate_name"]
        candidate = Candidate(
            external_candidate_id=row["external_candidate_id"],
            start_id=row.get("start_id"),
            candidate_name=name,
            normalized_name=name.strip().lower(),
            email=row.get("email"),
            client=row.get("client"),
            division=row.get("division") or version.division,
            status=row.get("status"),
            recruiter=row.get("recruiter"),
            pay_rate=row.get("pay_rate"),
            bill_rate=row.get("bill_rate"),
            margin=row.get("margin"),
            start_date=row.get("start_date"),
            source_version_id=version.id,
            last_touched_version_id=version.id,
            is_active=True,
            incentive_active=True,
        )
        db.add(candidate)
        created.append(candidate)
    version.row_count = len(created)
    db.flush()
    return created
