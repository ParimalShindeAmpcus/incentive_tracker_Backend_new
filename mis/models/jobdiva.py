from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mis.models.base import Base


class EmailImportLog(Base):
    __tablename__ = "email_import_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    run_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mailbox: Mapped[str | None] = mapped_column(String(150), nullable=True)
    message_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attachment_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inserted_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duplicate_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING", nullable=False)


class ImportedJobDivaRecord(Base):
    __tablename__ = "imported_jobdiva_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    activity_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    position_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    candidate_full_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    candidate_email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    candidate_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    candidate_state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    candidate_mobile_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    job_company: Mapped[str | None] = mapped_column(String(150), nullable=True)
    activity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    jobdiva_ref_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    recruited_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
    recruiter_email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(150), nullable=True)
    work_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    work_state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_client_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    work_authorization: Mapped[str | None] = mapped_column(String(100), nullable=True)
    organization_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("organizations.id"), nullable=True)
    import_batch_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("email_import_logs.id"), nullable=True)
    raw_row_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
