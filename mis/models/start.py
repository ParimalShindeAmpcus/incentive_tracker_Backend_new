from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from mis.models.base import Base

submission_status_enum = ENUM(
    "IMPORTED",
    "DRAFT",
    "SUBMITTED",
    "MANAGER_REVIEW",
    "MIS_REVIEW",
    "ONBOARDING_REVIEW",
    "APPROVED",
    "REJECTED",
    "COMPLETED",
    name="submission_status",
    create_type=False,
)


class CandidateStart(Base):
    __tablename__ = "candidate_start"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    imported_record_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("imported_jobdiva_records.id"), nullable=False
    )
    activity_id: Mapped[str] = mapped_column(String(50), nullable=False)
    organization_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("organizations.id"), nullable=False)
    recruiter_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    mapped_manager_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    submission_manager_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    candidate_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    candidate_email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    candidate_contact_no: Mapped[str | None] = mapped_column(String(30), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    end_client_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    contract_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sub_contractor_company: Mapped[str | None] = mapped_column(String(150), nullable=True)
    sub_contractor_email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    sub_contractor_contact: Mapped[str | None] = mapped_column(String(30), nullable=True)
    req_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(150), nullable=True)
    job_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    salary: Mapped[float | None] = mapped_column(Numeric(15, 3), nullable=True)
    pay_rate: Mapped[float | None] = mapped_column(Numeric(15, 3), nullable=True)
    taxes: Mapped[float | None] = mapped_column(Numeric(15, 3), nullable=True)
    benefits: Mapped[float | None] = mapped_column(Numeric(15, 3), nullable=True)
    referral_fee: Mapped[float | None] = mapped_column(Numeric(15, 3), nullable=True)
    gross_bill_rate: Mapped[float | None] = mapped_column(Numeric(15, 3), nullable=True)
    msp_fee: Mapped[float | None] = mapped_column(Numeric(15, 3), nullable=True)
    margin: Mapped[float | None] = mapped_column(Numeric(15, 3), nullable=True)
    margin_is_overridden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    remote_position: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    work_location: Mapped[str | None] = mapped_column(String(150), nullable=True)
    candidate_location: Mapped[str | None] = mapped_column(String(150), nullable=True)
    work_authorization: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resume_source: Mapped[str | None] = mapped_column(String(100), nullable=True)

    team_lead: Mapped[str | None] = mapped_column(String(150), nullable=True)
    crm: Mapped[str | None] = mapped_column(String(150), nullable=True)
    team_manager: Mapped[str | None] = mapped_column(String(150), nullable=True)
    head_of_department: Mapped[str | None] = mapped_column(String(150), nullable=True)
    senior_manager: Mapped[str | None] = mapped_column(String(150), nullable=True)
    associate_director: Mapped[str | None] = mapped_column(String(150), nullable=True)
    director: Mapped[str | None] = mapped_column(String(150), nullable=True)
    center_head: Mapped[str | None] = mapped_column(String(150), nullable=True)
    assistant_vice_president: Mapped[str | None] = mapped_column(String(150), nullable=True)
    onboarding_coordinator: Mapped[str | None] = mapped_column(String(150), nullable=True)

    user_email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    recruiter_location: Mapped[str | None] = mapped_column(String(150), nullable=True)

    status: Mapped[str] = mapped_column(submission_status_enum, default="DRAFT", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
