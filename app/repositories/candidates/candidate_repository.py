from datetime import date
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import func, or_

from sqlalchemy.orm import Session

from app.repositories.entities.candidate import Candidate, CandidateDataVersion


def list_candidates(
    db: Session,
    *,
    division: Optional[str] = None,
    project_status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> Tuple[List[Candidate], int]:
    q = db.query(Candidate)
    if division:
        q = q.filter(Candidate.division == division)
    if project_status:
        today = date.today()
        if project_status.upper() == "ENDED":
            q = q.filter(Candidate.end_date.isnot(None), Candidate.end_date <= today)
        elif project_status.upper() == "ACTIVE":
            q = q.filter(or_(Candidate.end_date.is_(None), Candidate.end_date > today))
    total = q.count()
    rows = q.order_by(Candidate.id).offset(skip).limit(limit).all()
    return rows, total


def list_all_candidates(db: Session, *, division: Optional[str] = None) -> List[Candidate]:
    q = db.query(Candidate)
    if division:
        q = q.filter(Candidate.division == division)
    return q.order_by(Candidate.id).all()


def list_candidates_for_cycle(
    db: Session,
    *,
    division: Optional[str] = None,
    version_id: Optional[int] = None,
) -> List[Candidate]:
    q = db.query(Candidate)
    if version_id:
        q = q.filter(Candidate.source_version_id == version_id)
    elif division:
        q = q.filter(Candidate.division == division)
    return q.order_by(Candidate.id).all()


def get_candidate(db: Session, candidate_id: int) -> Optional[Candidate]:
    return db.query(Candidate).filter(Candidate.id == candidate_id).first()


def get_candidate_by_external_id(db: Session, external_candidate_id: str) -> Optional[Candidate]:
    ext = (external_candidate_id or "").strip()
    if not ext:
        return None
    row = (
        db.query(Candidate)
        .filter(Candidate.external_candidate_id == ext)
        .order_by(Candidate.id.desc())
        .first()
    )
    if row is not None:
        return row
    # Case-insensitive / whitespace-tolerant fallback (VLOOKUP template IDs)
    return (
        db.query(Candidate)
        .filter(func.lower(Candidate.external_candidate_id) == ext.lower())
        .order_by(Candidate.id.desc())
        .first()
    )


def update_candidate(db: Session, candidate: Candidate, data: dict) -> Candidate:
    for key, value in data.items():
        if hasattr(candidate, key):
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


def find_existing_candidate(db: Session, row: dict) -> Optional[Candidate]:
    ext_id = str(row.get("external_candidate_id") or "").strip()
    act_id = str(row.get("activity_id") or "").strip()
    st_id = str(row.get("start_id") or "").strip()
    name = str(row.get("candidate_name") or "").strip().lower()
    client = str(row.get("client") or "").strip().lower()

    # 1. Match by activity_id, start_id, or external_candidate_id across all ID columns
    for test_id in (act_id, st_id, ext_id):
        if test_id and not test_id.startswith("AUTO-"):
            clean_id = test_id.lower()
            cand = db.query(Candidate).filter(
                or_(
                    func.lower(Candidate.activity_id) == clean_id,
                    func.lower(Candidate.start_id) == clean_id,
                    func.lower(Candidate.external_candidate_id) == clean_id,
                )
            ).first()
            if cand:
                return cand

    # 2. Match by normalized candidate name (+ optional client)
    if name:
        q = db.query(Candidate).filter(func.lower(Candidate.candidate_name) == name)
        if client:
            cand = q.filter(func.lower(Candidate.client) == client).first()
            if cand:
                return cand
        cand = q.first()
        if cand:
            return cand

    return None



def create_candidates(
    db: Session,
    version: CandidateDataVersion,
    rows: Sequence[dict],
) -> List[Candidate]:
    created: List[Candidate] = []
    for row in rows:
        name = row["candidate_name"]
        finders = row.get("finders_fee") or row.get("referral_fee")
        referral = row.get("referral_fee") or row.get("finders_fee")
        bill_rate_val = row.get("bill_rate") or row.get("gross_bill_rate")
        c_source = row.get("candidate_source") or row.get("resume_source")
        client_val = row.get("client")

        existing = find_existing_candidate(db, row)
        if existing:
            existing.last_touched_version_id = version.id
            is_prev_inactive = (
                existing.incentive_active is False
                or (existing.status and existing.status.upper() in {"LEFT", "MARKED LEFT", "INACTIVE (EXCLUDED)", "PROJECT ENDED"})
                or (existing.end_date and existing.end_date <= date.today())
            )

            if row.get("activity_id"):
                existing.activity_id = row.get("activity_id")
            if row.get("start_id"):
                existing.start_id = row.get("start_id")
            if row.get("email"):
                existing.email = row.get("email")
            if row.get("contact"):
                existing.contact = row.get("contact")
            if client_val:
                existing.client = client_val
                existing.normalized_client = client_val.strip().lower()
            if row.get("end_client"):
                existing.end_client = row.get("end_client")
            if row.get("job_title"):
                existing.job_title = row.get("job_title")
            if row.get("start_date"):
                existing.start_date = row.get("start_date")
            if row.get("end_date"):
                end_d = row.get("end_date")
                existing.end_date = end_d
                if end_d and end_d <= date.today():
                    existing.incentive_active = False
                    if not existing.status or existing.status == "Active":
                        existing.status = "Inactive (Excluded)"
                    if not existing.inactivation_reason:
                        existing.inactivation_reason = f"Project ended on {end_d}"

            if row.get("req_id"):
                existing.req_id = row.get("req_id")
            if row.get("contract_type"):
                existing.contract_type = row.get("contract_type")
            if row.get("subcontractor"):
                existing.subcontractor = row.get("subcontractor")
            if row.get("subcontractor_email"):
                existing.subcontractor_email = row.get("subcontractor_email")
            if row.get("subcontractor_contact"):
                existing.subcontractor_contact = row.get("subcontractor_contact")
            if row.get("job_level"):
                existing.job_level = row.get("job_level")
            if row.get("salary") is not None:
                existing.salary = row.get("salary")
            if row.get("pay_rate") is not None:
                existing.pay_rate = row.get("pay_rate")
            if row.get("taxes") is not None:
                existing.taxes = row.get("taxes")
            if row.get("benefits") is not None:
                existing.benefits = row.get("benefits")
            if referral is not None:
                existing.referral_fee = referral
            if finders is not None:
                existing.finders_fee = finders
            if bill_rate_val is not None:
                existing.bill_rate = bill_rate_val
            if row.get("msp_fee") is not None:
                existing.msp_fee = row.get("msp_fee")
            if row.get("margin") is not None:
                existing.margin = row.get("margin")
            if row.get("remote"):
                existing.remote = row.get("remote")
            if row.get("work_location"):
                existing.work_location = row.get("work_location")
            if row.get("candidate_location"):
                existing.candidate_location = row.get("candidate_location")
            if row.get("work_authorization"):
                existing.work_authorization = row.get("work_authorization")
            if c_source:
                existing.candidate_source = c_source
            if row.get("team_lead"):
                existing.team_lead = row.get("team_lead")
            if row.get("crm"):
                existing.crm = row.get("crm")
            if row.get("manager"):
                existing.manager = row.get("manager")
            if row.get("head_of_department"):
                existing.head_of_department = row.get("head_of_department")
            if row.get("senior_manager"):
                existing.senior_manager = row.get("senior_manager")
            if row.get("associate_director"):
                existing.associate_director = row.get("associate_director")
            if row.get("director"):
                existing.director = row.get("director")
            if row.get("center_head"):
                existing.center_head = row.get("center_head")
            if row.get("avp"):
                existing.avp = row.get("avp")
            if row.get("onboarding_coordinator"):
                existing.onboarding_coordinator = row.get("onboarding_coordinator")
            if row.get("organization"):
                existing.organization = row.get("organization")
            if row.get("user_email"):
                existing.user_email = row.get("user_email")
            if row.get("recruiter_location"):
                existing.recruiter_location = row.get("recruiter_location")
            if row.get("recruiter"):
                existing.recruiter = row.get("recruiter")
            if row.get("status") and not is_prev_inactive:
                existing.status = row.get("status")
            elif is_prev_inactive:
                existing.incentive_active = False
                if not existing.inactivation_reason:
                    existing.inactivation_reason = f"Project ended on {existing.end_date}" if existing.end_date else "Inactivated prior to bulk import"

            if row.get("placement_level"):
                existing.placement_level = row.get("placement_level")
            db.add(existing)
            created.append(existing)

        else:
            candidate = Candidate(
                external_candidate_id=row["external_candidate_id"],
                activity_id=row.get("activity_id"),
                start_id=row.get("start_id"),
                candidate_name=name,
                normalized_name=name.strip().lower(),
                email=row.get("email"),
                contact=row.get("contact"),
                client=client_val,
                normalized_client=client_val.strip().lower() if client_val else None,
                end_client=row.get("end_client"),
                job_title=row.get("job_title"),
                start_date=row.get("start_date"),
                end_date=row.get("end_date"),
                req_id=row.get("req_id"),
                contract_type=row.get("contract_type"),
                subcontractor=row.get("subcontractor"),
                subcontractor_email=row.get("subcontractor_email"),
                subcontractor_contact=row.get("subcontractor_contact"),
                job_level=row.get("job_level"),
                salary=row.get("salary"),
                pay_rate=row.get("pay_rate"),
                taxes=row.get("taxes"),
                benefits=row.get("benefits"),
                referral_fee=referral,
                finders_fee=finders,
                bill_rate=bill_rate_val,
                msp_fee=row.get("msp_fee"),
                margin=row.get("margin"),
                remote=row.get("remote"),
                work_location=row.get("work_location"),
                candidate_location=row.get("candidate_location"),
                work_authorization=row.get("work_authorization"),
                candidate_source=c_source,
                team_lead=row.get("team_lead"),
                crm=row.get("crm"),
                manager=row.get("manager"),
                head_of_department=row.get("head_of_department"),
                senior_manager=row.get("senior_manager"),
                associate_director=row.get("associate_director"),
                director=row.get("director"),
                center_head=row.get("center_head"),
                avp=row.get("avp"),
                onboarding_coordinator=row.get("onboarding_coordinator"),
                organization=row.get("organization"),
                user_email=row.get("user_email"),
                recruiter_location=row.get("recruiter_location"),
                recruiter=row.get("recruiter"),
                status=row.get("status"),
                placement_level=row.get("placement_level"),
                division=row.get("division") or version.division,
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
