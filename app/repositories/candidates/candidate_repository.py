from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, List, Optional, Sequence, Tuple

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
        q = q.filter(
            or_(
                Candidate.source_version_id == version_id,
                Candidate.last_touched_version_id == version_id,
            )
        )
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


def _clean_id(val) -> str:
    """Normalize an ID value: strip whitespace and fix Excel float artifacts like '1001.0' -> '1001'."""
    if val is None:
        return ""
    s = str(val).strip()
    # Normalize Excel numeric floats: "1001.0" -> "1001"
    if s and "." in s:
        try:
            f = float(s)
            if f == int(f):
                s = str(int(f))
        except (ValueError, OverflowError):
            pass
    return s


_PLACEHOLDER_VALUES = frozenset({
    "na", "n/a", "n.a.", "tbd", "pending", "--", "---", "-", "0",
    "none", "unknown", "null", "notapplicable", "nil", "blank",
})


def _is_placeholder_id(val) -> bool:
    """Return True if the value is missing, a known placeholder, or a manufactured prefix."""
    if val is None:
        return True
    s = _clean_id(val).lower()
    if not s:
        return True
    if s in _PLACEHOLDER_VALUES:
        return True
    if s.startswith("auto-") or s.startswith("cand-"):
        return True
    return False


def find_existing_candidate(db: Session, row: dict) -> Optional[Candidate]:
    """Option A strict zero-fallback matching.

    Priority 1: Valid start_id -> match ONLY Candidate.start_id
    Priority 2: Valid activity_id (only when no valid start_id) -> match ONLY Candidate.activity_id
    Priority 3: Return None (never match by name, external_candidate_id, or cross-field)
    """
    st_id = _clean_id(row.get("start_id"))
    act_id = _clean_id(row.get("activity_id"))

    # Priority 1: valid start_id
    if not _is_placeholder_id(st_id):
        return db.query(Candidate).filter(
            func.lower(Candidate.start_id) == st_id.lower()
        ).first()

    # Priority 2: valid activity_id (only when start_id is invalid/missing)
    if not _is_placeholder_id(act_id):
        return db.query(Candidate).filter(
            func.lower(Candidate.activity_id) == act_id.lower()
        ).first()

    # Priority 3: no valid identifier — return None
    return None


NUMERIC_FIELDS = {
    "salary",
    "pay_rate",
    "taxes",
    "benefits",
    "referral_fee",
    "finders_fee",
    "bill_rate",
    "msp_fee",
    "margin",
    "markup_percent",
    "approved_markup_percentage",
}

DATE_FIELDS = {
    "start_date",
    "end_date",
}

BOOLEAN_FIELDS = {
    "ownership_confirmed",
    "incentive_active",
    "is_active",
}


def values_differ(existing_val: Any, incoming_val: Any, field_name: str) -> bool:
    """Compare an existing DB value against an incoming value with type-aware normalization."""
    # 1. Non-clearable candidate_name: blank/None cell does NOT differ (preserves existing)
    if field_name == "candidate_name":
        if incoming_val is None or (isinstance(incoming_val, str) and incoming_val.strip() == ""):
            return False
        exist_str = (existing_val or "").strip()
        in_str = str(incoming_val).strip()
        return exist_str != in_str

    # 2. Matching Identifiers: start_id, activity_id (if incoming matches existing, no difference)
    if field_name in ("start_id", "activity_id"):
        if incoming_val is None or (isinstance(incoming_val, str) and incoming_val.strip() == ""):
            return False
        exist_str = (existing_val or "").strip().lower()
        in_str = str(incoming_val).strip().lower()
        return exist_str != in_str

    # 3. Numeric / Decimal fields: compare mathematically
    if field_name in NUMERIC_FIELDS:
        exist_is_empty = existing_val is None or (isinstance(existing_val, str) and existing_val.strip() == "")
        in_is_empty = incoming_val is None or (isinstance(incoming_val, str) and incoming_val.strip() == "")
        if exist_is_empty and in_is_empty:
            return False
        if exist_is_empty != in_is_empty:
            return True
        try:
            d_exist = Decimal(str(existing_val))
            d_in = Decimal(str(incoming_val))
            return d_exist != d_in
        except (InvalidOperation, ValueError, TypeError):
            return True

    # 4. Date fields: compare date objects
    if field_name in DATE_FIELDS:
        exist_is_empty = existing_val is None or (isinstance(existing_val, str) and existing_val.strip() == "")
        in_is_empty = incoming_val is None or (isinstance(incoming_val, str) and incoming_val.strip() == "")
        if exist_is_empty and in_is_empty:
            return False
        if exist_is_empty != in_is_empty:
            return True
        d_exist = existing_val
        if isinstance(d_exist, str):
            try:
                d_exist = datetime.strptime(d_exist[:10], "%Y-%m-%d").date()
            except Exception:
                pass
        d_in = incoming_val
        if isinstance(d_in, str):
            try:
                d_in = datetime.strptime(d_in[:10], "%Y-%m-%d").date()
            except Exception:
                pass
        return d_exist != d_in

    # 5. Boolean fields: compare boolean values
    if field_name in BOOLEAN_FIELDS:
        if existing_val is None and incoming_val is None:
            return False
        if incoming_val is None:
            return False
        b_in = bool(incoming_val)
        b_exist = bool(existing_val)
        return b_exist != b_in

    # 6. Default String / Categorical fields (e.g. job_title, client, email, etc.)
    # Treat None and empty string "" as equivalent empty states for clearable fields
    exist_empty = existing_val is None or (isinstance(existing_val, str) and existing_val.strip() == "")
    in_empty = incoming_val is None or (isinstance(incoming_val, str) and incoming_val.strip() == "")

    if exist_empty and in_empty:
        return False
    if exist_empty != in_empty:
        return True

    # Both non-empty: compare trimmed strings
    return str(existing_val).strip() != str(incoming_val).strip()


CLEARABLE_FIELDS = [
    "email",
    "contact",
    "client",
    "end_client",
    "job_title",
    "start_date",
    "end_date",
    "req_id",
    "contract_type",
    "subcontractor",
    "subcontractor_email",
    "subcontractor_contact",
    "job_level",
    "salary",
    "pay_rate",
    "taxes",
    "benefits",
    "referral_fee",
    "finders_fee",
    "finder_fees",
    "bill_rate",
    "msp_fee",
    "margin",
    "markup_percent",
    "approved_markup_percentage",
    "remote",
    "work_location",
    "candidate_location",
    "work_authorization",
    "candidate_source",
    "team_lead",
    "crm",
    "manager",
    "head_of_department",
    "senior_manager",
    "associate_director",
    "director",
    "center_head",
    "avp",
    "onboarding_coordinator",
    "organization",
    "user_email",
    "recruiter_location",
    "recruiter",
    "status",
    "placement_level",
    "division",
]


def create_candidates(
    db: Session,
    version: CandidateDataVersion,
    rows: Sequence[dict],
) -> Tuple[List[Candidate], List[Tuple[Candidate, List[str]]], List[Candidate], List[dict]]:
    new_candidates: List[Candidate] = []
    updated_candidates: List[Tuple[Candidate, List[str]]] = []
    duplicate_candidates: List[Candidate] = []
    rejected_rows: List[dict] = []

    # In-batch dedup maps (keyed by cleaned, lowercased ID)
    batch_by_start_id: dict[str, Candidate] = {}
    batch_by_activity_id: dict[str, Candidate] = {}

    for row_idx, row in enumerate(rows, start=1):
        raw_name = row.get("candidate_name")
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        c_source = row.get("candidate_source") or row.get("resume_source")
        client_val = row.get("client")

        st_id = _clean_id(row.get("start_id"))
        act_id = _clean_id(row.get("activity_id"))
        has_valid_start = not _is_placeholder_id(st_id)
        has_valid_activity = not _is_placeholder_id(act_id)

        # Option A: Reject rows missing both valid Start ID and Activity ID
        if not has_valid_start and not has_valid_activity:
            rejected_rows.append({
                "row": row_idx,
                "candidate_name": name,
                "status": "REJECTED",
                "reason": "Candidate row rejected: Missing valid Start ID or Activity ID. Candidate name cannot be used as an identifier.",
            })
            continue

        # Determine the lookup path and check in-batch maps first
        existing = None
        batch_key = ""
        used_start = False

        if has_valid_start:
            batch_key = st_id.lower()
            used_start = True
            if batch_key in batch_by_start_id:
                existing = batch_by_start_id[batch_key]
            else:
                existing = db.query(Candidate).filter(
                    func.lower(Candidate.start_id) == batch_key
                ).first()
        elif has_valid_activity:
            batch_key = act_id.lower()
            if batch_key in batch_by_activity_id:
                existing = batch_by_activity_id[batch_key]
            else:
                existing = db.query(Candidate).filter(
                    func.lower(Candidate.activity_id) == batch_key
                ).first()

        if existing:
            changed_fields: List[str] = []

            # 1. Non-clearable: candidate_name
            # If name is present and non-empty, update candidate_name and normalized_name.
            # If name is blank or null in the row, do NOT erase the existing name.
            if "candidate_name" in row:
                c_name = row["candidate_name"]
                if values_differ(existing.candidate_name, c_name, "candidate_name"):
                    existing.candidate_name = c_name.strip()
                    existing.normalized_name = c_name.strip().lower()
                    changed_fields.append("candidate_name")

            # 2. Matching Identifiers
            if "start_id" in row and has_valid_start:
                if values_differ(existing.start_id, st_id, "start_id"):
                    existing.start_id = st_id
                    changed_fields.append("start_id")
            if "activity_id" in row and has_valid_activity:
                if values_differ(existing.activity_id, act_id, "activity_id"):
                    existing.activity_id = act_id
                    changed_fields.append("activity_id")
            if "external_candidate_id" in row:
                ext_id = _clean_id(row.get("external_candidate_id"))
                ext_val = ext_id if (ext_id and not _is_placeholder_id(ext_id)) else None
                if values_differ(existing.external_candidate_id, ext_val, "external_candidate_id"):
                    existing.external_candidate_id = ext_val
                    changed_fields.append("external_candidate_id")

            # 3. Clearable fields: overwrite with value or clear to None if explicitly blank/null
            for field in CLEARABLE_FIELDS:
                if field in row:
                    val = row[field]
                    if values_differ(getattr(existing, field, None), val, field):
                        if val is None or (isinstance(val, str) and val.strip() == ""):
                            if hasattr(existing, field):
                                setattr(existing, field, None)
                            if field == "client":
                                existing.normalized_client = None
                        else:
                            cleaned = val.strip() if isinstance(val, str) else val
                            if hasattr(existing, field):
                                setattr(existing, field, cleaned)
                            if field == "client":
                                existing.normalized_client = str(cleaned).strip().lower()
                        changed_fields.append(field)

            # 4. Special cases
            if "resume_source" in row and "candidate_source" not in row:
                rs_val = row["resume_source"]
                if values_differ(existing.candidate_source, rs_val, "candidate_source"):
                    if rs_val is None or (isinstance(rs_val, str) and rs_val.strip() == ""):
                        existing.candidate_source = None
                    else:
                        existing.candidate_source = rs_val.strip() if isinstance(rs_val, str) else rs_val
                    changed_fields.append("candidate_source")

            if "ownership_confirmed" in row and row["ownership_confirmed"] is not None:
                if values_differ(existing.ownership_confirmed, row["ownership_confirmed"], "ownership_confirmed"):
                    existing.ownership_confirmed = bool(row["ownership_confirmed"])
                    changed_fields.append("ownership_confirmed")
            if "incentive_active" in row and row["incentive_active"] is not None:
                if values_differ(existing.incentive_active, row["incentive_active"], "incentive_active"):
                    existing.incentive_active = bool(row["incentive_active"])
                    changed_fields.append("incentive_active")
            if "inactivation_reason" in row:
                if values_differ(existing.inactivation_reason, row["inactivation_reason"], "inactivation_reason"):
                    existing.inactivation_reason = row["inactivation_reason"]
                    changed_fields.append("inactivation_reason")

            if changed_fields:
                existing.last_touched_version_id = version.id
                db.add(existing)
                updated_candidates.append((existing, changed_fields))
            else:
                duplicate_candidates.append(existing)

            # Register in batch maps
            if used_start:
                batch_by_start_id[batch_key] = existing
            else:
                batch_by_activity_id[batch_key] = existing

        else:
            if not name:
                rejected_rows.append({
                    "row": row_idx,
                    "candidate_name": "",
                    "status": "REJECTED",
                    "reason": "Candidate name is required for new candidate",
                })
                continue

            # Store external_candidate_id only if genuinely provided
            ext_id = _clean_id(row.get("external_candidate_id"))
            ext_id_val = ext_id if (ext_id and not _is_placeholder_id(ext_id)) else None

            candidate = Candidate(
                external_candidate_id=ext_id_val,
                activity_id=act_id if has_valid_activity else None,
                start_id=st_id if has_valid_start else None,
                candidate_name=name,
                normalized_name=name.strip().lower() if name else "",
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
                referral_fee=row.get("referral_fee"),
                finders_fee=row.get("finders_fee"),
                finder_fees=row.get("finder_fees") or "NONE",
                bill_rate=row.get("bill_rate"),
                msp_fee=row.get("msp_fee"),
                margin=row.get("margin"),
                markup_percent=row.get("markup_percent"),
                approved_markup_percentage=row.get("approved_markup_percentage"),
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
                is_active=row.get("is_active", True),
                incentive_active=row.get("incentive_active", True),
                inactivation_reason=row.get("inactivation_reason"),
                ownership_confirmed=bool(row.get("ownership_confirmed", False)),
            )
            db.add(candidate)
            new_candidates.append(candidate)

            # Register in batch maps
            if used_start:
                batch_by_start_id[batch_key] = candidate
            else:
                batch_by_activity_id[batch_key] = candidate

    version.row_count = len(new_candidates) + len(updated_candidates) + len(duplicate_candidates)
    db.flush()
    return new_candidates, updated_candidates, duplicate_candidates, rejected_rows

