import csv, io
from typing import Optional

from openpyxl import load_workbook
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.coordinators.schemas import CoordinatorInput, CoordinatorStatusUpdate, CoordinatorUpdate
from app.repositories.coordinators import coordinator_repository as repo
from app.repositories.entities.audit import AuditAction
from app.repositories.entities.coordinator import CoordinatorRecord, CoordinatorStatus
from app.repositories.entities.user import User
from app.services.audit import audit_service

def norm(value: str): return " ".join(value.strip().lower().split())
def apply_status(record, status_value, exit_date):
    record.employment_status = CoordinatorStatus.LEFT if exit_date else status_value
    record.exit_date = exit_date
    record.incentive_eligible = record.employment_status == CoordinatorStatus.ACTIVE

def _status_label(value) -> str:
    return value.value if hasattr(value, "value") else str(value)

def list_coordinators(db: Session, page: int, page_size: int, search: Optional[str], employment_status: Optional[CoordinatorStatus]):
    return {"items": repo.list_records(db, (page-1)*page_size, page_size, search, employment_status), "total": repo.count(db, search, employment_status), "page": page, "page_size": page_size}
def get_coordinator(db, record_id):
    record = repo.get(db, record_id)
    if not record: raise HTTPException(status_code=404, detail="Coordinator not found")
    return record
def summary(db):
    counts = repo.counts(db); return {"total_coordinators": sum(counts.values()), "active_coordinators": counts["ACTIVE"], "left_coordinators": counts["LEFT"], "notice_period_coordinators": counts["NOTICE"], "incentive_eligible_coordinators": counts["ACTIVE"]}
def create(db: Session, payload: CoordinatorInput, user: Optional[User] = None, record_audit: bool = True):
    email = str(payload.email).lower()
    if repo.by_email(db, email): raise HTTPException(status_code=409, detail="A coordinator with this email already exists")
    record = CoordinatorRecord(full_name=payload.full_name.strip(), normalized_name=norm(payload.full_name), email=email, organization=payload.organization.strip(), role_title=payload.role_title.strip(), start_date=payload.start_date, bank_name=payload.bank_name, account_number=payload.account_number, ifsc_code=payload.ifsc_code.upper() if payload.ifsc_code else None)
    apply_status(record, payload.employment_status, payload.exit_date); db.add(record)
    if record_audit:
        audit_service.record_event(
            db,
            action=AuditAction.COORDINATOR_ADD,
            title=f"Added coordinator {record.full_name}",
            details=f"Created {record.full_name} ({record.email}) as {_status_label(record.employment_status)} in {record.organization}",
            user=user,
            metadata={"email": record.email, "organization": record.organization, "role": record.role_title},
            entity_type="coordinator",
        )
    db.commit(); db.refresh(record); return record
def update(db: Session, record_id: int, payload: CoordinatorUpdate, user: Optional[User] = None):
    record = get_coordinator(db, record_id); data = payload.model_dump(exclude_unset=True)
    previous_status = record.employment_status
    previous_name = record.full_name
    if "email" in data and data["email"]:
        existing = repo.by_email(db, str(data["email"]).lower())
        if existing and existing.id != record.id: raise HTTPException(status_code=409, detail="A coordinator with this email already exists")
        record.email = str(data.pop("email")).lower()
    if "full_name" in data and data["full_name"]: record.full_name=data["full_name"].strip(); record.normalized_name=norm(record.full_name)
    for field in ("organization", "role_title", "start_date", "bank_name", "account_number", "ifsc_code"):
        if field in data: setattr(record, field, data[field].strip().upper() if field == "ifsc_code" and data[field] else data[field])
    apply_status(record, data.get("employment_status", record.employment_status), data.get("exit_date", record.exit_date))
    status_changed = previous_status != record.employment_status or "exit_date" in payload.model_dump(exclude_unset=True)
    if status_changed:
        title = f"Coordinator status changed: {record.full_name}"
        details = f"Changed {record.full_name} from {_status_label(previous_status)} to {_status_label(record.employment_status)}"
    else:
        title = f"Updated coordinator {record.full_name}"
        details = f"Updated coordinator record for {record.full_name} ({record.email})"
    audit_service.record_event(
        db,
        action=AuditAction.COORDINATOR_TOGGLE,
        title=title,
        details=details,
        user=user,
        metadata={"coordinator_id": record.id, "previous_status": _status_label(previous_status), "status": _status_label(record.employment_status)},
        entity_type="coordinator",
        entity_id=str(record.id),
    )
    db.commit(); db.refresh(record); return record
def update_status(db, record_id, payload: CoordinatorStatusUpdate, user: Optional[User] = None):
    return update(db, record_id, CoordinatorUpdate(employment_status=payload.employment_status, exit_date=payload.exit_date), user=user)
def delete_left(db, record_id, user: Optional[User] = None):
    record = get_coordinator(db, record_id)
    if record.employment_status != CoordinatorStatus.LEFT: raise HTTPException(status_code=422, detail="Only coordinators marked Left can be deleted")
    name, email = record.full_name, record.email
    record.is_deleted = True
    audit_service.record_event(
        db,
        action=AuditAction.COORDINATOR_DELETE,
        title=f"Deleted left coordinator {name}",
        details=f"Removed left coordinator {name} ({email}) from the directory",
        user=user,
        metadata={"email": email},
        entity_type="coordinator",
        entity_id=str(record_id),
    )
    db.commit()
def _rows(content: bytes, filename: str):
    if filename.lower().endswith(".xlsx"):
        sheet = load_workbook(io.BytesIO(content), data_only=True).active
        values = list(sheet.iter_rows(values_only=True))
        if not values:
            return []
        headers = [str(value or "").strip() for value in values[0]]
        return [dict(zip(headers, ["" if value is None else str(value) for value in row])) for row in values[1:]]
    return list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
def bulk_upload(db, content: bytes, filename: str, user: Optional[User] = None):
    issues=[]; created=0
    for index,row in enumerate(_rows(content, filename), 2):
        try:
            payload=CoordinatorInput(full_name=row.get("Coordinator Name") or row.get("Full Name") or "", email=row.get("Email") or "", organization=row.get("Organization") or "", role_title=row.get("Role") or row.get("Role / Title") or "", employment_status=row.get("Employment Status") or "ACTIVE", exit_date=row.get("Exit Date") or None, bank_name=row.get("Bank Name") or None, account_number=row.get("Account Number") or None, ifsc_code=row.get("IFSC Code") or None)
            create(db, payload, user=user, record_audit=False); created+=1
        except (ValidationError, HTTPException) as exc: issues.append({"source_row":index,"identifier":row.get("Email") or row.get("Coordinator Name") or f"Row {index}","reason":str(getattr(exc,"detail",exc))})
    audit_service.record_event(
        db,
        action=AuditAction.FILE_UPLOAD,
        title="Uploaded coordinator list",
        details=f"Imported {created} coordinator(s) from {filename}",
        user=user,
        metadata={"filename": filename, "created_count": created, "issue_count": len(issues)},
        entity_type="coordinator_upload",
    )
    if created:
        audit_service.record_event(
            db,
            action=AuditAction.COORDINATOR_ADD,
            title=f"Added {created} coordinator(s) from bulk upload",
            details=f"Created {created} coordinator record(s) from {filename}",
            user=user,
            metadata={"filename": filename, "created_count": created},
            entity_type="coordinator_upload",
        )
    db.commit()
    return {"created_count":created,"issues":issues}
def bulk_mark_left(db, content: bytes, filename: str, user: Optional[User] = None):
    issues=[]; changed=0
    for index,row in enumerate(_rows(content, filename), 2):
        email=(row.get("Email") or "").strip().lower()
        if not email: issues.append({"source_row":index,"identifier":f"Row {index}","reason":"Email address is blank"}); continue
        record=repo.by_email(db,email)
        if not record: issues.append({"source_row":index,"identifier":email,"reason":"Email was not found"}); continue
        if record.employment_status != CoordinatorStatus.LEFT: apply_status(record,CoordinatorStatus.LEFT,None); changed+=1
    audit_service.record_event(
        db,
        action=AuditAction.FILE_UPLOAD,
        title="Uploaded left-coordinator file",
        details=f"Processed {filename} and marked {changed} coordinator(s) as Left",
        user=user,
        metadata={"filename": filename, "marked_left_count": changed, "issue_count": len(issues)},
        entity_type="coordinator_upload",
    )
    if changed:
        audit_service.record_event(
            db,
            action=AuditAction.COORDINATOR_TOGGLE,
            title=f"Marked {changed} coordinator(s) as Left",
            details=f"Employment status set to Left for {changed} coordinator(s) from {filename}",
            user=user,
            metadata={"filename": filename, "marked_left_count": changed},
            entity_type="coordinator_upload",
        )
    db.commit(); return {"marked_left_count":changed,"issues":issues}
