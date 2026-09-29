"""Application-wide constants aligned with schema enums."""

SUBMISSION_STATUSES = (
    "IMPORTED",
    "DRAFT",
    "SUBMITTED",
    "MANAGER_REVIEW",
    "MIS_REVIEW",
    "ONBOARDING_REVIEW",
    "APPROVED",
    "REJECTED",
    "COMPLETED",
)

ROLE_CODES = (
    "RECRUITER",
    "MANAGER",
    "MIS",
    "HOD",
    "ONBOARD_TEAM",
    "TEAM_LEAD",
    "CRM",
    "SENIOR_MANAGER",
    "ASSOCIATE_DIRECTOR",
    "DIRECTOR",
    "CENTER_HEAD",
    "AVP",
)

# HOD inherits former manager review capabilities (MANAGER/TEAM_LEAD kept for legacy users)
HOD_LIKE_ROLES = frozenset({"HOD", "MANAGER", "TEAM_LEAD"})
# Only HOD may approve/edit recruiter submissions; Manager is view + create only
HOD_APPROVER_ROLES = frozenset({"HOD"})
ONBOARD_ROLES = frozenset({"ONBOARD_TEAM"})
NON_LEADERSHIP_ROLES = frozenset({"RECRUITER", "ONBOARD_TEAM", "MIS"})
HOD_REVIEWABLE_STATUSES = frozenset({"SUBMITTED", "MANAGER_REVIEW"})
ONBOARD_REVIEWABLE_STATUSES = frozenset({"ONBOARDING_REVIEW"})
ADMIN_REVIEWABLE_STATUSES = frozenset({"MIS_REVIEW"})
START_NOTIFICATION_TYPES = ("START_APPROVED", "START_PENDING", "START_UPDATED")


def is_leadership_role(role_code: str | None) -> bool:
    """Return whether a role belongs in the leadership workspace.

    Leadership roles can be added through Master Data, so they cannot be kept in
    a fixed allow-list. Administrative, recruiting and onboarding roles remain
    explicitly outside this workspace.
    """
    normalized = (role_code or "").strip().upper()
    return bool(normalized) and normalized not in NON_LEADERSHIP_ROLES

DROPDOWN_CATEGORIES = (
    "CONTRACT_TYPE",
    "JOB_LEVEL",
    "RESUME_SOURCE",
    "WORK_AUTHORIZATION",
    "RECRUITER_LOCATION",
    "TEAM",
    "TAXES_ADMIN_PAYROLL_CHARGES",
)

# Margin formula (must match frontend calculateMargin)
# Contract Placements (W2, C2C, T4):
# net_bill_rate = gross_bill_rate - (gross_bill_rate * msp_fee / 100)
# pay_burden = pay_rate + (pay_rate * taxes / 100)
# margin = net_bill_rate - pay_burden - benefits - referral_fee
# FTE / SOW: Not applicable -> margin = 0.0


def calculate_margin(
    contract_type: str | None,
    gross_bill_rate: float | None,
    msp_fee_pct: float | None,
    pay_rate: float | None,
    tax_pct: float | None,
    benefits: float | None,
    referral_fee: float | None,
) -> float:
    if (contract_type or "").strip().upper() in {"FTE", "SOW"}:
        return 0.0

    gross = gross_bill_rate or 0.0
    msp = msp_fee_pct or 0.0
    pay = pay_rate or 0.0
    tax = tax_pct or 0.0
    benefit = benefits or 0.0
    ref = referral_fee or 0.0

    net_bill_rate = gross - (gross * msp / 100.0)
    pay_burden = pay + (pay * tax / 100.0)
    margin = net_bill_rate - pay_burden - benefit - ref

    return round(margin, 3)

