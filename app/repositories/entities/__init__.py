"""SQLAlchemy ORM entities — import side-effects register tables on Base.metadata."""

from app.repositories.entities.audit import AuditAction, AuditLog
from app.repositories.entities.coordinator import CoordinatorRecord, CoordinatorStatus
from app.repositories.entities.candidate import Candidate, CandidateDataVersion
from app.repositories.entities.cycle import (
    CycleChecklistItem,
    CycleDataSnapshot,
    CycleHoursMatch,
    CycleManualAdjustment,
    CyclePaymentStatus,
    CycleStatus,
    CycleValidationResult,
    IncentiveCycle,
    MatchResult,
)
from app.repositories.entities.hours import HoursBenchmark, HoursDataVersion, HoursRow
from app.repositories.entities.incentive import (
    IncentiveApproval,
    IncentiveLine,
    IncentivePayment,
    IncentiveSlab,
    PaidIncentiveLedger,
)
from app.repositories.entities.organization import Division, Employee, Organization
from app.repositories.entities.project_end import ProjectEndRecord, ProjectEndVersion
from app.repositories.entities.recruiter import (
    RecruiterMasterVersion,
    RecruiterStatus,
    RecruiterStatusEnum,
)
from app.repositories.entities.user import Role, User, user_roles

__all__ = [
    "AuditAction",
    "AuditLog",
    "Candidate",
    "CandidateDataVersion",
    "CycleChecklistItem",
    "CycleDataSnapshot",
    "CycleHoursMatch",
    "CycleManualAdjustment",
    "CyclePaymentStatus",
    "CycleStatus",
    "CycleValidationResult",
    "IncentiveCycle",
    "MatchResult",
    "HoursBenchmark",
    "HoursDataVersion",
    "HoursRow",
    "IncentiveApproval",
    "IncentiveLine",
    "IncentivePayment",
    "IncentiveSlab",
    "PaidIncentiveLedger",
    "Division",
    "Employee",
    "Organization",
    "ProjectEndRecord",
    "ProjectEndVersion",
    "RecruiterMasterVersion",
    "RecruiterStatus",
    "RecruiterStatusEnum",
    "Role",
    "User",
    "user_roles",
]
