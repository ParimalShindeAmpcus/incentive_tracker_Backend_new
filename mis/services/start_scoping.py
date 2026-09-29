"""Strict role-based scoping and authorization helpers for CandidateStart records."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, or_

from mis.core.constants import (
    ADMIN_REVIEWABLE_STATUSES,
    HOD_APPROVER_ROLES,
    HOD_REVIEWABLE_STATUSES,
    ONBOARD_REVIEWABLE_STATUSES,
    ONBOARD_ROLES,
)
from mis.models.start import CandidateStart

if TYPE_CHECKING:
    from mis.models.user import User

ADMIN_ROLE_CODES = frozenset({"MIS"})
HOD_REVIEWABLE_SET = set(HOD_REVIEWABLE_STATUSES)
ONBOARD_REVIEWABLE_SET = set(ONBOARD_REVIEWABLE_STATUSES)
ALL_REVIEWABLE_SET = HOD_REVIEWABLE_SET | ONBOARD_REVIEWABLE_SET | set(ADMIN_REVIEWABLE_STATUSES)

HIERARCHY_COLUMNS = (
    CandidateStart.head_of_department,
    CandidateStart.team_manager,
    CandidateStart.onboarding_coordinator,
    CandidateStart.team_lead,
    CandidateStart.crm,
    CandidateStart.senior_manager,
    CandidateStart.associate_director,
    CandidateStart.director,
    CandidateStart.center_head,
    CandidateStart.assistant_vice_president,
)


def build_start_visibility_conditions(user: User) -> list:
    """Build SQLAlchemy filter conditions enforcing strict role-based data access.

    1. Super Admin, MIS, HR (ADMIN_ROLE_CODES): No scoping filters (global access).
    2. Recruiter: Only New Starts created/assigned to themselves.
    3. HOD, Onboarding, Manager, Team Lead, CRM, Senior Manager, Associate Director,
       Director, Center Head, AVP: Only New Starts where their own user name is
       assigned/mentioned.
    """
    role_code = (user.role.code if user.role else "").upper().strip()

    # Admin roles (MIS, HR, ADMIN) have full visibility
    if role_code in ADMIN_ROLE_CODES:
        return []

    user_email = (user.email or "").strip().lower()
    user_name = (user.full_name or "").strip().lower()

    if role_code == "RECRUITER":
        creator_conditions = [CandidateStart.recruiter_id == user.id]
        if user.id:
            creator_conditions.append(CandidateStart.created_by == user.id)
        if user_email:
            creator_conditions.append(
                func.lower(func.trim(CandidateStart.user_email)) == user_email
            )
        return [or_(*creator_conditions)]

    # For all leadership, HOD, manager, director, team lead, onboarding roles:
    # Can view ONLY New Starts where their own user name is assigned/mentioned.
    if not user_name:
        return [CandidateStart.id == -1]

    name_conditions = [
        func.lower(func.trim(col)) == user_name
        for col in HIERARCHY_COLUMNS
    ]
    return [or_(*name_conditions)]


def can_user_view_start(
    start: CandidateStart,
    user: User,
    is_ampcus_tech: bool = False,
) -> bool:
    """Check if the user is authorized to view a specific start record."""
    role_code = (user.role.code if user.role else "").upper().strip()

    # Ampcus Tech segregation: onboard team cannot view Ampcus Tech starts
    if is_ampcus_tech and role_code in ONBOARD_ROLES:
        return False

    if role_code in ADMIN_ROLE_CODES:
        return True

    user_email = (user.email or "").strip().lower()
    user_name = (user.full_name or "").strip().lower()
    start_user_email = (start.user_email or "").strip().lower()

    # Recruiter can view only New Starts created/assigned to themselves
    if role_code == "RECRUITER":
        return bool(
            start.recruiter_id == user.id
            or (start.created_by is not None and start.created_by == user.id)
            or (user_email and start_user_email == user_email)
        )

    # Leadership, HOD, Manager, Director, Team Lead, CRM, Onboard, etc.:
    # Can view ONLY New Starts where their own user name is assigned/mentioned
    if user_name:
        hierarchy_values = (
            start.head_of_department,
            start.team_manager,
            start.onboarding_coordinator,
            start.team_lead,
            start.crm,
            start.senior_manager,
            start.associate_director,
            start.director,
            start.center_head,
            start.assistant_vice_president,
        )
        for val in hierarchy_values:
            if val and val.strip().lower() == user_name:
                return True

    return False


def can_user_review_start(
    start: CandidateStart,
    user: User,
    is_ampcus_tech: bool = False,
) -> bool:
    """Check if the user is authorized to review (approve/reject) a start record."""
    role_code = (user.role.code if user.role else "").upper().strip()
    user_name = (user.full_name or "").strip().lower()

    # For Ampcus Tech Client & Inhouse: Admin and Onboard must NOT review or approve
    if is_ampcus_tech:
        if role_code in ONBOARD_ROLES:
            return False
        if role_code in ADMIN_ROLE_CODES:
            return False

    # Cannot review own submission
    if start.recruiter_id == user.id or (start.created_by is not None and start.created_by == user.id):
        return False

    # Platform Admins can review standard non-Ampcus starts
    if role_code in ADMIN_ROLE_CODES:
        return True

    hod_name = (start.head_of_department or "").strip().lower()
    is_designated_hod = bool(user_name and hod_name == user_name)

    # HOD Review
    if role_code in HOD_APPROVER_ROLES or is_designated_hod:
        if start.status not in HOD_REVIEWABLE_SET:
            return False
        return is_designated_hod

    # Onboarding Team Review
    if role_code in ONBOARD_ROLES:
        if start.status not in ONBOARD_REVIEWABLE_SET:
            return False
        coord_name = (start.onboarding_coordinator or "").strip().lower()
        return bool(user_name and coord_name == user_name)

    return False


def can_user_edit_start(
    start: CandidateStart,
    user: User,
    is_ampcus_tech: bool = False,
) -> bool:
    """Check if the user is authorized to edit a start record."""
    role_code = (user.role.code if user.role else "").upper().strip()
    user_name = (user.full_name or "").strip().lower()

    if role_code in ADMIN_ROLE_CODES:
        return True

    # User cannot edit/approve their own submission during review
    if start.recruiter_id == user.id or (start.created_by is not None and start.created_by == user.id):
        return False

    if start.status not in ALL_REVIEWABLE_SET:
        return False

    hod_name = (start.head_of_department or "").strip().lower()
    is_designated_hod = bool(user_name and hod_name == user_name)

    if (role_code in HOD_APPROVER_ROLES or is_designated_hod) and is_designated_hod:
        return True

    if role_code in ONBOARD_ROLES:
        coord_name = (start.onboarding_coordinator or "").strip().lower()
        return bool(user_name and coord_name == user_name)

    return False
