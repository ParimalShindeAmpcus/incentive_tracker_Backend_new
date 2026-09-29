"""SQLAlchemy ORM entities — import side-effects register tables on Base.metadata."""

from prism.repositories.entities.audit import AuditAction, AuditLog
from prism.repositories.entities.coordinator import CoordinatorRecord, CoordinatorStatus
from prism.repositories.entities.candidate import Candidate, CandidateDataVersion
from prism.repositories.entities.cycle import (
    CycleApprovalResult,
    CycleChecklistItem,
    CycleHoursMatch,
    CycleManualAdjustment,
    CyclePaymentStatus,
    CycleStatus,
    CycleValidationResult,
    IncentiveCycle,
    MatchResult,
)
from prism.repositories.entities.hours import HoursBenchmark, HoursDataVersion, HoursRow
from prism.repositories.entities.incentive import (
    IncentiveLine,
    IncentiveSlab,
)
from prism.repositories.entities.organization import Division, Organization
from prism.repositories.entities.project_end import ProjectEndRecord, ProjectEndVersion
from prism.repositories.entities.user import Role, User, user_roles
from prism.repositories.entities.vlookup import (
    VLookupMatchedRecord,
    VLookupTemplateCandidate,
    VLookupUploadBatch,
    VLookupWeeklyHours,
)
from prism.repositories.entities.auth_revocation import RevokedToken

__all__ = [
    "AuditAction",
    "AuditLog",
    "Candidate",
    "CandidateDataVersion",
    "CycleApprovalResult",
    "CycleChecklistItem",
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
    "IncentiveLine",
    "IncentiveSlab",
    "Division",
    "Organization",
    "ProjectEndRecord",
    "ProjectEndVersion",
    "Role",
    "User",
    "user_roles",
    "VLookupMatchedRecord",
    "VLookupTemplateCandidate",
    "VLookupUploadBatch",
    "VLookupWeeklyHours",
    "RevokedToken",
]
