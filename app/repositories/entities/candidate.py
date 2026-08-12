from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class CandidateDataVersion(Base):
    __tablename__ = "candidate_data_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_label: Mapped[str] = mapped_column(String(100), nullable=False)
    source_filename: Mapped[Optional[str]] = mapped_column(String(255))
    division: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    candidates: Mapped[List["Candidate"]] = relationship(
        "Candidate",
        back_populates="source_version",
        foreign_keys="Candidate.source_version_id",
    )


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_candidate_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    activity_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    start_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    candidate_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    contact: Mapped[Optional[str]] = mapped_column(String(50))
    client: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    end_client: Mapped[Optional[str]] = mapped_column(String(255))
    normalized_client: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    job_title: Mapped[Optional[str]] = mapped_column(String(255))
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    req_id: Mapped[Optional[str]] = mapped_column(String(100))
    contract_type: Mapped[Optional[str]] = mapped_column(String(50))
    subcontractor: Mapped[Optional[str]] = mapped_column(String(255))
    subcontractor_email: Mapped[Optional[str]] = mapped_column(String(255))
    subcontractor_contact: Mapped[Optional[str]] = mapped_column(String(50))
    job_level: Mapped[Optional[str]] = mapped_column(String(100))
    salary: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    pay_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    taxes: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    benefits: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    referral_fee: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    finders_fee: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    bill_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    msp_fee: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    margin: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    markup_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    remote: Mapped[Optional[str]] = mapped_column(String(20))
    work_location: Mapped[Optional[str]] = mapped_column(String(255))
    candidate_location: Mapped[Optional[str]] = mapped_column(String(255))
    work_authorization: Mapped[Optional[str]] = mapped_column(String(100))
    candidate_source: Mapped[Optional[str]] = mapped_column(String(255))
    team_lead: Mapped[Optional[str]] = mapped_column(String(255))
    crm: Mapped[Optional[str]] = mapped_column(String(255))
    manager: Mapped[Optional[str]] = mapped_column(String(255))
    head_of_department: Mapped[Optional[str]] = mapped_column(String(255))
    senior_manager: Mapped[Optional[str]] = mapped_column(String(255))
    associate_director: Mapped[Optional[str]] = mapped_column(String(255))
    director: Mapped[Optional[str]] = mapped_column(String(255))
    center_head: Mapped[Optional[str]] = mapped_column(String(255))
    avp: Mapped[Optional[str]] = mapped_column(String(255))
    onboarding_coordinator: Mapped[Optional[str]] = mapped_column(String(255))
    organization: Mapped[Optional[str]] = mapped_column(String(255))
    user_email: Mapped[Optional[str]] = mapped_column(String(255))
    recruiter_location: Mapped[Optional[str]] = mapped_column(String(255))
    recruiter: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[Optional[str]] = mapped_column(String(100))
    placement_level: Mapped[Optional[str]] = mapped_column(String(50))
    division: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    source_version_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_data_versions.id"), nullable=False
    )
    last_touched_version_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_data_versions.id"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    incentive_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    inactivation_reason: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    source_version: Mapped[CandidateDataVersion] = relationship(
        "CandidateDataVersion",
        foreign_keys=[source_version_id],
        back_populates="candidates",
    )
    last_touched_version: Mapped[CandidateDataVersion] = relationship(
        "CandidateDataVersion",
        foreign_keys=[last_touched_version_id],
    )
