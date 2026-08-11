from io import BytesIO, StringIO

from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.audit import AuditAction
from app.models.user import User
from app.repositories import cycle_repo
from app.services import audit_service


def export_cycle(db: Session, cycle_id: int, user: User, *, fmt: str = "xlsx") -> tuple[bytes, str, str]:
    cycle = cycle_repo.get_cycle(db, cycle_id)
    if not cycle:
        raise NotFoundError(f"Cycle {cycle_id} not found")
    lines = cycle_repo.list_lines(db, cycle_id)
    headers = [
        "Line ID",
        "Candidate ID",
        "Candidate Name",
        "Role",
        "Person",
        "Type",
        "Eligible",
        "Amount",
        "Hours",
        "Margin",
        "Payment Status",
        "Rule",
    ]
    rows = [
        [
            l.id,
            l.candidate_id,
            l.candidate_name,
            l.role,
            l.person,
            l.incentive_type,
            l.eligible,
            float(l.amount),
            float(l.hours) if l.hours is not None else None,
            float(l.margin) if l.margin is not None else None,
            l.payment_status,
            l.rule_applied,
        ]
        for l in lines
    ]
    audit_service.write(
        db,
        action=AuditAction.EXPORT,
        user_id=user.id,
        entity_type="incentive_cycle",
        entity_id=str(cycle_id),
        details=f"Export format={fmt}",
        commit=True,
    )
    if fmt.lower() == "csv":
        buf = StringIO()
        buf.write(",".join(headers) + "\n")
        for row in rows:
            buf.write(",".join("" if v is None else str(v) for v in row) + "\n")
        data = buf.getvalue().encode("utf-8")
        return data, "text/csv", f"cycle_{cycle_id}.csv"

    wb = Workbook()
    ws = wb.active
    ws.title = "Incentive Lines"
    ws.append(headers)
    for row in rows:
        ws.append(row)
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue(), (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ), f"cycle_{cycle_id}.xlsx"
