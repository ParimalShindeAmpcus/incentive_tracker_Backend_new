from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mis.models.base import Base


class OnboardingOrganization(Base):
    __tablename__ = "onboarding_organizations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    mappings: Mapped[list["OnboardingOrganizationMapping"]] = relationship(
        back_populates="onboarding_organization"
    )


class OnboardingOrganizationMapping(Base):
    __tablename__ = "onboarding_organization_mappings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    onboarding_organization_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("onboarding_organizations.id"), nullable=False
    )
    organization_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organizations.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    onboarding_organization: Mapped["OnboardingOrganization"] = relationship(
        back_populates="mappings"
    )
