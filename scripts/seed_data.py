"""
Unified Seed Data Script for Starts MIS & PRISM Platform.

This single standalone script seeds test users, roles, organizations, master data,
and sample workflow records for both New Starts (MIS) and PRISM applications.

Usage:
    python scripts/seed_data.py                 # Seeds both MIS and PRISM
    python scripts/seed_data.py --mis-only      # Seeds only Starts MIS
    python scripts/seed_data.py --prism-only    # Seeds only PRISM
    python scripts/seed_data.py --reset-passwords # Resets all test passwords
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Fix for passlib compatibility with bcrypt >= 4.1.0
try:
    import bcrypt
    if not hasattr(bcrypt, "__about__"):
        bcrypt.__about__ = type("about", (), {"__version__": getattr(bcrypt, "__version__", "4.0.0")})
except Exception:
    pass

try:
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    from mis.core.config import settings as mis_settings
    from mis.core.security import hash_password as mis_hash_password
    from prism.config import get_settings as get_prism_settings
    from prism.security.auth import hash_password as prism_hash_password
except ImportError as e:
    print(f"\n[ERROR] Missing required dependency: {e}")
    print("[TIP] Please run with your virtual environment:")
    print("      .\\venv\\Scripts\\python.exe seed_data.py")
    print("      or activate it first: .\\venv\\Scripts\\activate\n")
    sys.exit(1)



DEFAULT_MIS_PASSWORD = "Pass@123"
DEFAULT_PRISM_PASSWORD = "Admin@123"


def get_connection(db_name: str | None = None):
    target_db = db_name or mis_settings.DB_NAME or "mis_prism_db"
    conn = psycopg2.connect(
        host=mis_settings.DB_HOST,
        port=mis_settings.PORT,
        user=mis_settings.DB_USER,
        password=mis_settings.PASSWORD,
        dbname=target_db,
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    return conn


# ==============================================================================
# PART 1: SEED STARTS MIS (Schema: mis)
# ==============================================================================

MIS_ROLES = [
    ("MIS", "Admin"),
    ("RECRUITER", "Recruiter"),
    ("MANAGER", "Manager"),
    ("HOD", "HOD"),
    ("ONBOARD_TEAM", "Onboard Team"),
    ("TEAM_LEAD", "Team Lead"),
    ("CRM", "CRM"),
    ("SENIOR_MANAGER", "Senior Manager"),
    ("ASSOCIATE_DIRECTOR", "Associate Director"),
    ("DIRECTOR", "Director"),
    ("CENTER_HEAD", "Center Head"),
    ("AVP", "AVP"),
]

MIS_ORGANIZATIONS = [
    ("AMPCUS_INC", "Ampcus Inc"),
    ("AMPCUS_TECH", "Ampcus Tech"),
    ("AMPCUS_CYBER", "Ampcus Cyber"),
    ("BRAVENS_INC", "Bravens Inc"),
    ("APOKRIN_LLC", "Apokrin LLC"),
    ("ITECH_INC", "ITech Inc")
]

MIS_ONBOARDING_ORGS = [
    ("BRAVENS_ONBOARD", "Bravens Inc (Onboarding)"),
    ("AMPCUS_ONBOARD", "Ampcus Inc (Onboarding)"),
]

MIS_DROPDOWNS = [
    # CONTRACT_TYPE
    ("CONTRACT_TYPE", "W2", 1),
    ("CONTRACT_TYPE", "C2C", 2),
    ("CONTRACT_TYPE", "T4", 3),
    ("CONTRACT_TYPE", "FTE", 4),
    ("CONTRACT_TYPE", "SOW", 5),
    # JOB_LEVEL
    ("JOB_LEVEL", "Junior", 1),
    ("JOB_LEVEL", "Mid", 2),
    ("JOB_LEVEL", "Mid-Level", 3),
    ("JOB_LEVEL", "Senior", 4),
    ("JOB_LEVEL", "Lead", 5),
    ("JOB_LEVEL", "Architect", 6),
    ("JOB_LEVEL", "Manager", 7),
    ("JOB_LEVEL", "Director", 8),
    ("JOB_LEVEL", "NA", 9),
    # RESUME_SOURCE
    ("RESUME_SOURCE", "LinkedIn", 1),
    ("RESUME_SOURCE", "LinkedIn RPS", 2),
    ("RESUME_SOURCE", "Dice", 3),
    ("RESUME_SOURCE", "Monster", 4),
    ("RESUME_SOURCE", "Indeed", 5),
    ("RESUME_SOURCE", "CareerBuilder", 6),
    ("RESUME_SOURCE", "Referral", 7),
    ("RESUME_SOURCE", "Internal Database", 8),
    ("RESUME_SOURCE", "Company Website", 9),
    ("RESUME_SOURCE", "JobDiva", 10),
    ("RESUME_SOURCE", "Other", 11),
    # WORK_AUTHORIZATION
    ("WORK_AUTHORIZATION", "US Citizen", 1),
    ("WORK_AUTHORIZATION", "Green Card", 2),
    ("WORK_AUTHORIZATION", "GC", 3),
    ("WORK_AUTHORIZATION", "H1B", 4),
    ("WORK_AUTHORIZATION", "OPT", 5),
    ("WORK_AUTHORIZATION", "TN", 6),
    ("WORK_AUTHORIZATION", "CPT/OPT", 7),
    ("WORK_AUTHORIZATION", "H4 EAD", 8),
    ("WORK_AUTHORIZATION", "L2 EAD", 9),
    ("WORK_AUTHORIZATION", "EAD", 10),
    ("WORK_AUTHORIZATION", "Canadian Citizen", 11),
    # RECRUITER_LOCATION
    ("RECRUITER_LOCATION", "Nashik", 1),
    ("RECRUITER_LOCATION", "Sambhaji Nagar", 3),
    ("RECRUITER_LOCATION", "Pune", 3),
    ("RECRUITER_LOCATION", "Hyderabad", 4),
    # TEAM
    ("TEAM", "Alpha", 1),
    ("TEAM", "Bravo", 2),
    # TAXES_ADMIN_PAYROLL_CHARGES
    ("TAXES_ADMIN_PAYROLL_CHARGES", "0", 1),
    ("TAXES_ADMIN_PAYROLL_CHARGES", "5", 2),
    ("TAXES_ADMIN_PAYROLL_CHARGES", "15.4", 3),
    ("TAXES_ADMIN_PAYROLL_CHARGES", "20.4", 4),
    # ORGANIZATION
    ("ORGANIZATION", "Ampcus Inc", 1),
    ("ORGANIZATION", "Ampcus Tech", 2),
    ("ORGANIZATION", "Ampcus Cyber", 3),
    ("ORGANIZATION", "Bravens Inc", 4),
    ("ORGANIZATION", "Apokrin LLC", 5),
    ("ORGANIZATION", "ITech Inc", 6),
    # EMPLOYMENT_TYPE
    ("EMPLOYMENT_TYPE", "Full Time", 1),
    ("EMPLOYMENT_TYPE", "Part Time", 2),
    ("EMPLOYMENT_TYPE", "Contract", 3),
    # WORK_LOCATION
    ("WORK_LOCATION", "Remote", 1),
    ("WORK_LOCATION", "Onsite", 2),
    ("WORK_LOCATION", "Hybrid", 3),
    # CITIZENSHIP_STATUS
    ("CITIZENSHIP_STATUS", "US Citizen", 1),
    ("CITIZENSHIP_STATUS", "Green Card", 2),
    ("CITIZENSHIP_STATUS", "H1B", 3),
    ("CITIZENSHIP_STATUS", "CPT/OPT", 4),
    ("CITIZENSHIP_STATUS", "EAD", 5),
    ("CITIZENSHIP_STATUS", "Canadian Citizen", 6),
    # REASON_FOR_BENCH
    ("REASON_FOR_BENCH", "Project Ended", 1),
    ("REASON_FOR_BENCH", "Bench Consultant", 2),
    ("REASON_FOR_BENCH", "Resigned", 3),
    ("REASON_FOR_BENCH", "Performance Issue", 4),
    # INCENTIVE_TYPE
    ("INCENTIVE_TYPE", "Regular", 1),
    ("INCENTIVE_TYPE", "One-Time", 2),
    ("INCENTIVE_TYPE", "Milestone", 3),
    # SOURCING_TYPE
    ("SOURCING_TYPE", "JobDiva", 1),
    ("SOURCING_TYPE", "LinkedIn", 2),
    ("SOURCING_TYPE", "Dice", 3),
    ("SOURCING_TYPE", "Monster", 4),
    ("SOURCING_TYPE", "Referral", 5),
    ("SOURCING_TYPE", "Internal", 6),
    # MARGIN_REMARKS
    ("MARGIN_REMARKS", "Standard", 1),
    ("MARGIN_REMARKS", "Approved by VP", 2),
    ("MARGIN_REMARKS", "Special Margin", 3),
    # CURRENCY
    ("CURRENCY", "USD", 1),
    ("CURRENCY", "INR", 2)
]

USERS = [
    {
        "full_name": "System Admin",
        "email": "admin@example.com",
        "role": "MIS",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        "is_super_admin": True,
    },
    {
        "full_name": "Arjun Singh",
        "email": "recruiter1@bravens.com",
        "role": "RECRUITER",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Neha Patel",
        "email": "recruiter2@bravens.com",
        "role": "RECRUITER",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Rohit Sharma",
        "email": "recruiter3@bravens.com",
        "role": "RECRUITER",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Priya Desai",
        "email": "recruiter4@bravens.com",
        "role": "RECRUITER",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Amit Kumar",
        "email": "recruiter5@bravens.com",
        "role": "RECRUITER",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Sanjay Mehta",
        "email": "hod1@bravens.com",
        "role": "HOD",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Anita Rao",
        "email": "hod2@bravens.com",
        "role": "HOD",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Vikram Gupta",
        "email": "hod3@bravens.com",
        "role": "HOD",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Sneha Nair",
        "email": "onboarding1@bravens.com",
        "role": "ONBOARD_TEAM",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Rahul Verma",
        "email": "onboarding2@bravens.com",
        "role": "ONBOARD_TEAM",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Divya Joshi",
        "email": "onboarding3@bravens.com",
        "role": "ONBOARD_TEAM",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Deepak Kumar",
        "email": "admin1@bravens.com",
        "role": "MIS",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        "is_super_admin": True,
    },
    {
        "full_name": "Meera Iyer",
        "email": "admin2@bravens.com",
        "role": "MIS",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        "is_super_admin": True,
    },
    {
        "full_name": "Karan Malhotra",
        "email": "manager1@bravens.com",
        "role": "MANAGER",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Pooja Reddy",
        "email": "manager2@bravens.com",
        "role": "MANAGER",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Vivek Chauhan",
        "email": "teamlead1@bravens.com",
        "role": "TEAM_LEAD",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Shreya Kapoor",
        "email": "teamlead2@bravens.com",
        "role": "TEAM_LEAD",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Manoj Tiwari",
        "email": "crm1@bravens.com",
        "role": "CRM",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Kavita Bhatia",
        "email": "crm2@bravens.com",
        "role": "CRM",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Rajesh Khanna",
        "email": "seniormanager1@bravens.com",
        "role": "SENIOR_MANAGER",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Sunita Agarwal",
        "email": "seniormanager2@bravens.com",
        "role": "SENIOR_MANAGER",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Ashwin Menon",
        "email": "associatedirector1@bravens.com",
        "role": "ASSOCIATE_DIRECTOR",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Ritu Chawla",
        "email": "associatedirector2@bravens.com",
        "role": "ASSOCIATE_DIRECTOR",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Nikhil Bansal",
        "email": "director1@bravens.com",
        "role": "DIRECTOR",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Alka Saxena",
        "email": "director2@bravens.com",
        "role": "DIRECTOR",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Suresh Pillai",
        "email": "centerhead1@bravens.com",
        "role": "CENTER_HEAD",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Geeta Krishnan",
        "email": "centerhead2@bravens.com",
        "role": "CENTER_HEAD",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Harsh Vardhan",
        "email": "avp1@bravens.com",
        "role": "AVP",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        },
    {
        "full_name": "Nandini Pillai",
        "email": "avp2@bravens.com",
        "role": "AVP",
        "org": "Ampcus Inc",
        "team": "Alpha",
        "password": "Pass@123",
        }
]


def seed_mis(conn, reset_passwords: bool = False):
    print("\n--- Seeding Starts MIS (Schema: mis) ---")
    cur = conn.cursor()
    cur.execute("SET search_path = mis, public;")

    # 1. Organizations
    print("  -> Seeding organizations...")
    org_ids = {}
    for code, name in MIS_ORGANIZATIONS:
        cur.execute("SELECT id FROM organizations WHERE code = %s;", (code,))
        row = cur.fetchone()
        if not row:
            cur.execute(
                "INSERT INTO organizations (code, name, is_active) VALUES (%s, %s, TRUE) RETURNING id;",
                (code, name),
            )
            org_ids[code] = cur.fetchone()[0]
        else:
            org_ids[code] = row[0]
            cur.execute("UPDATE organizations SET name = %s, is_active = TRUE WHERE id = %s;", (name, row[0]))

    # 2. Roles
    print("  -> Seeding roles...")
    role_ids = {}
    for code, name in MIS_ROLES:
        cur.execute("SELECT id FROM roles WHERE code = %s;", (code,))
        row = cur.fetchone()
        if not row:
            cur.execute("INSERT INTO roles (code, name) VALUES (%s, %s) RETURNING id;", (code, name))
            role_ids[code] = cur.fetchone()[0]
        else:
            role_ids[code] = row[0]
            cur.execute("UPDATE roles SET name = %s WHERE id = %s;", (name, row[0]))

    # 3. Onboarding Organizations & Mappings
    print("  -> Seeding onboarding organizations...")
    onboard_ids = {}
    for code, name in MIS_ONBOARDING_ORGS:
        cur.execute("SELECT id FROM onboarding_organizations WHERE code = %s;", (code,))
        row = cur.fetchone()
        if not row:
            cur.execute(
                "INSERT INTO onboarding_organizations (code, name, is_active) VALUES (%s, %s, TRUE) RETURNING id;",
                (code, name),
            )
            onboard_ids[code] = cur.fetchone()[0]
        else:
            onboard_ids[code] = row[0]
            cur.execute("UPDATE onboarding_organizations SET name = %s, is_active = TRUE WHERE id = %s;", (name, row[0]))

    # Mappings
    bravens_onboard_id = onboard_ids.get("BRAVENS_ONBOARD")
    if bravens_onboard_id:
        for org_code in ["BRAVENS_INC", "APOKRIN_LLC"]:
            oid = org_ids.get(org_code)
            if oid:
                cur.execute(
                    """
                    INSERT INTO onboarding_organization_mappings (onboarding_organization_id, organization_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING;
                    """,
                    (bravens_onboard_id, oid),
                )

    ampcus_onboard_id = onboard_ids.get("AMPCUS_ONBOARD")
    if ampcus_onboard_id:
        for org_code in ["AMPCUS_INC", "AMPCUS_TECH", "AMPCUS_CYBER", "ITECH_INC"]:
            oid = org_ids.get(org_code)
            if oid:
                cur.execute(
                    """
                    INSERT INTO onboarding_organization_mappings (onboarding_organization_id, organization_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING;
                    """,
                    (ampcus_onboard_id, oid),
                )

    # 4. Dropdowns
    print("  -> Seeding dropdown master entries...")
    for category, value, order in MIS_DROPDOWNS:
        cur.execute(
            """
            INSERT INTO dropdown_master (category, value, display_order, is_active)
            SELECT %s, %s, %s, TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM dropdown_master WHERE category = %s AND lower(value) = lower(%s)
            );
            """,
            (category, value, order, category, value),
        )

    # 5. Clean up old test users not in USERS list
    new_emails = [u["email"].lower().strip() for u in USERS]
    cur.execute("SELECT id, email FROM users WHERE email NOT IN %s;", (tuple(new_emails),))
    obsolete_users = cur.fetchall()
    if obsolete_users:
        obs_ids = [row[0] for row in obsolete_users]
        cur.execute("DELETE FROM recruiter_manager_mapping WHERE recruiter_id = ANY(%s) OR manager_id = ANY(%s);", (obs_ids, obs_ids))
        cur.execute("DELETE FROM notifications WHERE user_id = ANY(%s);", (obs_ids,))
        cur.execute("DELETE FROM password_reset_tokens WHERE user_id = ANY(%s);", (obs_ids,))
        cur.execute("DELETE FROM audit_logs WHERE actor_id = ANY(%s);", (obs_ids,))
        cur.execute("DELETE FROM approvals WHERE actor_id = ANY(%s);", (obs_ids,))
        cur.execute("DELETE FROM incentives WHERE recruiter_id = ANY(%s) OR manager_id = ANY(%s);", (obs_ids, obs_ids))
        cur.execute("SELECT id FROM users WHERE email = 'recruiter1@bravens.com';")
        r_row = cur.fetchone()
        fallback_rec_id = r_row[0] if r_row else None

        cur.execute("SELECT id FROM users WHERE email = 'manager1@bravens.com';")
        m_row = cur.fetchone()
        fallback_mgr_id = m_row[0] if m_row else None

        if fallback_rec_id:
            cur.execute("UPDATE candidate_start SET recruiter_id = %s WHERE recruiter_id = ANY(%s);", (fallback_rec_id, obs_ids))
        else:
            cur.execute("DELETE FROM candidate_start WHERE recruiter_id = ANY(%s);", (obs_ids,))

        if fallback_mgr_id:
            cur.execute("UPDATE candidate_start SET mapped_manager_id = %s WHERE mapped_manager_id = ANY(%s);", (fallback_mgr_id, obs_ids))
            cur.execute("UPDATE candidate_start SET submission_manager_id = %s WHERE submission_manager_id = ANY(%s);", (fallback_mgr_id, obs_ids))
        else:
            cur.execute("UPDATE candidate_start SET mapped_manager_id = NULL WHERE mapped_manager_id = ANY(%s);", (obs_ids,))
            cur.execute("UPDATE candidate_start SET submission_manager_id = NULL WHERE submission_manager_id = ANY(%s);", (obs_ids,))

        cur.execute("UPDATE candidate_start SET created_by = NULL WHERE created_by = ANY(%s);", (obs_ids,))
        cur.execute("UPDATE candidate_start SET updated_by = NULL WHERE updated_by = ANY(%s);", (obs_ids,))
        cur.execute("DELETE FROM users WHERE id = ANY(%s);", (obs_ids,))

    # 6. Seed USERS
    print(f"  -> Seeding MIS test users ({len(USERS)} users, Default password: {DEFAULT_MIS_PASSWORD})...")
    cur.execute("UPDATE users SET employee_code = 'TEMP-' || id;")
    user_ids = {}

    for idx, u in enumerate(USERS):
        email = u["email"].lower().strip()
        full_name = u["full_name"]
        role_code = u["role"]
        rid = role_ids.get(role_code, role_ids.get("RECRUITER"))
        oid = org_ids.get("AMPCUS_INC", 1)
        onboard_id = ampcus_onboard_id if role_code == "ONBOARD_TEAM" else None
        team_name = u.get("team", "Alpha")
        emp_code = f"EMP-{idx + 1:03d}"
        user_pw = u.get("password", DEFAULT_MIS_PASSWORD)
        user_pw_hash = mis_hash_password(user_pw)
        is_super = u.get("is_super_admin", False)

        cur.execute("SELECT id FROM users WHERE email = %s;", (email,))
        row = cur.fetchone()
        if not row:
            cur.execute(
                """
                INSERT INTO users (
                    organization_id, role_id, onboarding_organization_id,
                    employee_code, full_name, email, password_hash, team_name,
                    is_active, is_super_admin
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
                RETURNING id;
                """,
                (oid, rid, onboard_id, emp_code, full_name, email, user_pw_hash, team_name, is_super),
            )
            user_ids[email] = cur.fetchone()[0]
        else:
            user_ids[email] = row[0]
            cur.execute(
                """
                UPDATE users SET 
                    organization_id = %s,
                    role_id = %s,
                    onboarding_organization_id = %s,
                    employee_code = %s,
                    full_name = %s,
                    password_hash = %s,
                    team_name = %s,
                    is_active = TRUE,
                    is_super_admin = %s
                WHERE id = %s;
                """,
                (oid, rid, onboard_id, emp_code, full_name, user_pw_hash, team_name, is_super, row[0]),
            )

    # 7. Recruiter-Manager Mapping
    print("  -> Seeding recruiter-manager mappings...")
    ampcus_org_id = org_ids.get("AMPCUS_INC", 1)
    rec1_id = user_ids.get("recruiter1@bravens.com")
    rec2_id = user_ids.get("recruiter2@bravens.com")
    rec3_id = user_ids.get("recruiter3@bravens.com")
    rec4_id = user_ids.get("recruiter4@bravens.com")
    rec5_id = user_ids.get("recruiter5@bravens.com")
    mgr1_id = user_ids.get("manager1@bravens.com")
    mgr2_id = user_ids.get("manager2@bravens.com")

    cur.execute("DELETE FROM recruiter_manager_mapping;")
    mappings = []
    for r_id, m_id, o_id in mappings:
        if r_id and m_id:
            cur.execute(
                """
                INSERT INTO recruiter_manager_mapping (recruiter_id, manager_id, organization_id, is_active)
                VALUES (%s, %s, %s, TRUE);
                """,
                (r_id, m_id, o_id),
            )

    # 7.5 Email Import Logs (Mock Automated Ingestion Batch)
    batch_id = None

    # 8. Sample Starts (Submissions)
    print("  -> Seeding sample candidate starts...")
    sample_starts = []

    start_ids = {}
    for (
        act_id,
        c_name,
        c_email,
        ctype,
        client,
        end_client,
        title,
        s_date,
        prate,
        brate,
        margin,
        stat,
        rec_id,
        mgr_id,
        r_source,
        w_auth,
        r_loc,
        w_loc,
        c_loc,
        sub_comp,
        sub_email,
        sub_phone,
    ) in sample_starts:
        if not rec_id or not mgr_id:
            continue

        # 1. Ensure imported JobDiva record exists
        cur.execute("SELECT id FROM imported_jobdiva_records WHERE activity_id = %s;", (act_id,))
        job_row = cur.fetchone()
        if not job_row:
            cur.execute(
                """
                INSERT INTO imported_jobdiva_records (
                    activity_id, candidate_full_name, candidate_email,
                    job_company, job_title, start_date, end_client_name,
                    organization_id, import_batch_id, is_consumed
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                RETURNING id;
                """,
                (
                    act_id,
                    c_name,
                    c_email,
                    client,
                    title,
                    s_date,
                    end_client,
                    ampcus_org_id,
                    batch_id,
                ),
            )
            imported_id = cur.fetchone()[0]
        else:
            imported_id = job_row[0]
            cur.execute(
                """
                UPDATE imported_jobdiva_records SET
                    candidate_full_name = %s,
                    candidate_email = %s,
                    job_company = %s,
                    job_title = %s,
                    start_date = %s,
                    end_client_name = %s,
                    import_batch_id = COALESCE(import_batch_id, %s)
                WHERE id = %s;
                """,
                (c_name, c_email, client, title, s_date, end_client, batch_id, imported_id),
            )

        # 2. Insert or update candidate start
        cur.execute("SELECT id FROM candidate_start WHERE activity_id = %s;", (act_id,))
        start_row = cur.fetchone()
        if not start_row:
            cur.execute(
                """
                INSERT INTO candidate_start (
                    imported_record_id, activity_id, organization_id, recruiter_id,
                    mapped_manager_id, submission_manager_id,
                    candidate_name, candidate_email, contract_type, client_name, end_client_name,
                    job_title, start_date, pay_rate, gross_bill_rate, margin, status,
                    resume_source, work_authorization, recruiter_location, work_location, candidate_location,
                    sub_contractor_company, sub_contractor_email, sub_contractor_contact,
                    team_manager, head_of_department, team_lead, crm, onboarding_coordinator
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    'Karan Malhotra', 'Sanjay Mehta', 'Vivek Chauhan', 'Manoj Tiwari', 'Sneha Nair'
                ) RETURNING id;
                """,
                (
                    imported_id,
                    act_id,
                    ampcus_org_id,
                    rec_id,
                    mgr_id,
                    mgr_id,
                    c_name,
                    c_email,
                    ctype,
                    client,
                    end_client,
                    title,
                    s_date,
                    prate,
                    brate,
                    margin,
                    stat,
                    r_source,
                    w_auth,
                    r_loc,
                    w_loc,
                    c_loc,
                    sub_comp,
                    sub_email,
                    sub_phone,
                ),
            )
            start_ids[act_id] = cur.fetchone()[0]
        else:
            start_ids[act_id] = start_row[0]
            cur.execute(
                """
                UPDATE candidate_start SET
                    recruiter_id = %s,
                    mapped_manager_id = %s,
                    submission_manager_id = %s,
                    organization_id = %s,
                    candidate_name = %s,
                    candidate_email = %s,
                    contract_type = %s,
                    client_name = %s,
                    end_client_name = %s,
                    job_title = %s,
                    start_date = %s,
                    pay_rate = %s,
                    gross_bill_rate = %s,
                    margin = %s,
                    status = %s,
                    resume_source = %s,
                    work_authorization = %s,
                    recruiter_location = %s,
                    work_location = %s,
                    candidate_location = %s,
                    sub_contractor_company = %s,
                    sub_contractor_email = %s,
                    sub_contractor_contact = %s,
                    team_manager = 'Karan Malhotra',
                    head_of_department = 'Sanjay Mehta',
                    team_lead = 'Vivek Chauhan',
                    crm = 'Manoj Tiwari',
                    onboarding_coordinator = 'Sneha Nair'
                WHERE id = %s;
                """,
                (
                    rec_id,
                    mgr_id,
                    mgr_id,
                    ampcus_org_id,
                    c_name,
                    c_email,
                    ctype,
                    client,
                    end_client,
                    title,
                    s_date,
                    prate,
                    brate,
                    margin,
                    stat,
                    r_source,
                    w_auth,
                    r_loc,
                    w_loc,
                    c_loc,
                    sub_comp,
                    sub_email,
                    sub_phone,
                    start_row[0],
                ),
            )

    # 9. Subcontractors
    print("  -> Seeding subcontractors...")
    admin1_id = user_ids.get("admin1@bravens.com")
    subcontractors = []
    for name, email, phone in subcontractors:
        cur.execute("SELECT id FROM subcontractors WHERE name = %s;", (name,))
        s_row = cur.fetchone()
        if not s_row:
            cur.execute(
                """
                INSERT INTO subcontractors (organization_id, name, email, contact_phone, is_active, created_by)
                VALUES (%s, %s, %s, %s, TRUE, %s);
                """,
                (ampcus_org_id, name, email, phone, admin1_id),
            )
        else:
            cur.execute(
                """
                UPDATE subcontractors SET 
                    organization_id = %s, email = %s, contact_phone = %s, is_active = TRUE 
                WHERE id = %s;
                """,
                (ampcus_org_id, email, phone, s_row[0]),
            )

    # 10. Email Templates
    print("  -> Seeding email templates...")
    email_templates = [
        (
            "START_CREATED",
            "Start Form Created",
            "New Candidate Start Submitted: {{candidate_name}}",
            "<p>Hello,</p><p>A new start has been recorded for <strong>{{candidate_name}}</strong> (Activity: {{activity_id}}) at {{client_name}}.</p>",
        ),
        (
            "MANAGER_APPROVAL_REQUEST",
            "Manager Review Request",
            "Action Required: Review Candidate Start {{activity_id}}",
            "<p>Hello Manager,</p><p>Please review and approve the candidate start for <strong>{{candidate_name}}</strong>.</p>",
        ),
        (
            "MIS_APPROVAL_REQUEST",
            "MIS Review Request",
            "MIS Verification Required: {{activity_id}}",
            "<p>Hello MIS Team,</p><p>Manager approval has completed for <strong>{{candidate_name}}</strong>. Please perform MIS verification.</p>",
        ),
        (
            "START_APPROVED",
            "Start Approved",
            "Candidate Start Approved: {{candidate_name}}",
            "<p>Congratulations,</p><p>The start form for <strong>{{candidate_name}}</strong> has been fully approved.</p>",
        ),
        (
            "START_REJECTED",
            "Start Rejected",
            "Candidate Start Rejected: {{candidate_name}}",
            "<p>Notice: The start form for {{candidate_name}} was rejected. Reason: {{rejection_reason}}.</p>",
        ),
    ]
    for code, name, subject, body in email_templates:
        cur.execute("SELECT id FROM email_templates WHERE code = %s;", (code,))
        et_row = cur.fetchone()
        if not et_row:
            cur.execute(
                """
                INSERT INTO email_templates (organization_id, code, name, subject, body_html, is_active, created_by)
                VALUES (%s, %s, %s, %s, %s, TRUE, %s);
                """,
                (ampcus_org_id, code, name, subject, body, admin1_id),
            )
        else:
            cur.execute(
                """
                UPDATE email_templates SET 
                    organization_id = %s, name = %s, subject = %s, body_html = %s, is_active = TRUE
                WHERE id = %s;
                """,
                (ampcus_org_id, name, subject, body, et_row[0]),
            )

    # 11. App Settings
    print("  -> Seeding application settings...")
    app_settings = [
        (
            "MARGIN_THRESHOLD_SETTINGS",
            '{"min_margin": 15.0, "high_margin": 30.0, "requires_vp_approval": 10.0}',
        ),
        (
            "EMAIL_INGESTION_CONFIG",
            '{"sync_interval_minutes": 30, "auto_match": true, "sender_whitelist": ["jobdiva@ampcus.com"]}',
        ),
        (
            "PORTAL_BRANDING",
            '{"portal_name": "Starts MIS", "theme": "dark", "company_name": "Ampcus Inc"}',
        ),
    ]
    for key, val_json in app_settings:
        cur.execute("SELECT id FROM app_settings WHERE key = %s AND organization_id = %s;", (key, ampcus_org_id))
        st_row = cur.fetchone()
        if not st_row:
            cur.execute(
                """
                INSERT INTO app_settings (organization_id, key, value_json, updated_by)
                VALUES (%s, %s, %s::jsonb, %s);
                """,
                (ampcus_org_id, key, val_json, admin1_id),
            )
        else:
            cur.execute(
                """
                UPDATE app_settings SET value_json = %s::jsonb, updated_by = %s WHERE id = %s;
                """,
                (val_json, admin1_id, st_row[0]),
            )

    # 12. Incentives & Approvals for Sample Starts
    # Mock data removed

    # 13. Notifications
    print("  -> Seeding sample notifications...")
    notifications = []
    for uid, s_id, n_type, title, msg in notifications:
        if uid:
            cur.execute(
                """
                INSERT INTO notifications (user_id, candidate_start_id, type, title, message, is_read)
                SELECT %s, %s, %s, %s, %s, FALSE
                WHERE NOT EXISTS (
                    SELECT 1 FROM notifications WHERE user_id = %s AND title = %s
                );
                """,
                (uid, s_id, n_type, title, msg, uid, title),
            )

    # 14. Audit Logs
    print("  -> Seeding audit log history...")
    cur.execute("DELETE FROM audit_logs;")
    audit_samples = []
    for org_id, actor_id, ent_type, ent_id, action, before_j, after_j in audit_samples:
        if ent_id and actor_id:
            cur.execute(
                """
                INSERT INTO audit_logs (organization_id, actor_id, entity_type, entity_id, action, before_json, after_json)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb);
                """,
                (org_id, actor_id, ent_type, ent_id, action, before_j, after_j),
            )

    # 15. Password Reset Tokens
    # Mock data removed

    cur.close()
    print("  [OK] Starts MIS seeding completed successfully.")


# ==============================================================================
# PART 2: SEED PRISM (Schema: prism)
# ==============================================================================

PRISM_DIVISIONS = [
    ("nashik", "Nashik Division"),
    ("sambhajiNagar", "Sambhaji Nagar Division"),
    ("ampcusTechClient", "Ampcus Tech Client"),
    ("ampcusTechInhouse", "Ampcus Tech In-House"),
]

PRISM_ADMINS = [
    ("admin@example.com", "Default Admin")
]

NASHIK_SLABS = [
    (Decimal("1.00"), Decimal("2.00"), Decimal("500")),
    (Decimal("2.01"), Decimal("4.00"), Decimal("1000")),
    (Decimal("4.01"), Decimal("6.00"), Decimal("1500")),
    (Decimal("6.01"), Decimal("8.00"), Decimal("2000")),
    (Decimal("8.01"), Decimal("10.00"), Decimal("2500")),
    (Decimal("10.01"), Decimal("15.00"), Decimal("3500")),
    (Decimal("15.01"), Decimal("20.00"), Decimal("4000")),
    (Decimal("20.01"), Decimal("30.00"), Decimal("4500")),
    (Decimal("30.01"), Decimal("40.00"), Decimal("7000")),
    (Decimal("40.01"), Decimal("50.00"), Decimal("10000")),
]


def seed_prism(conn, reset_passwords: bool = False):
    print("\n--- Seeding PRISM (Schema: prism) ---")

    # 1. Use the official PRISM seed service to seed roles, admin users, org, divisions, benchmarks, and all slabs
    try:
        from prism.services.common.seed import seed_database as seed_prism_database
        seed_prism_database()
        print("  -> PRISM roles, admin accounts, organizations, benchmarks, and slabs initialized.")
    except Exception as e:
        print(f"  [WARN] Note on PRISM seed service: {e}")

    cur = conn.cursor()
    cur.execute("SET search_path = prism, public;")

    # Ensure organization & divisions exist with is_active = TRUE
    print("  -> Ensuring PRISM organization and divisions...")
    cur.execute("SELECT id FROM organizations WHERE code = 'DEFAULT';")
    row = cur.fetchone()
    if not row:
        cur.execute(
            "INSERT INTO organizations (code, name, is_active) VALUES ('DEFAULT', 'Default Organization', TRUE) RETURNING id;"
        )
        org_id = cur.fetchone()[0]
    else:
        org_id = row[0]

    div_ids = {}
    for code, name in PRISM_DIVISIONS:
        cur.execute("SELECT id FROM divisions WHERE code = %s AND organization_id = %s;", (code, org_id))
        r = cur.fetchone()
        if not r:
            cur.execute(
                "INSERT INTO divisions (organization_id, code, name, is_active) VALUES (%s, %s, %s, TRUE) RETURNING id;",
                (org_id, code, name),
            )
            div_ids[code] = cur.fetchone()[0]
        else:
            div_ids[code] = r[0]

    # Hours Benchmarks
    print("  -> Ensuring PRISM hours benchmarks (160h)...")
    for code, name in PRISM_DIVISIONS:
        cur.execute(
            """
            INSERT INTO hours_benchmarks (division, benchmark_hours, description, is_active)
            SELECT %s, 160.00, %s, TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM hours_benchmarks WHERE division = %s
            );
            """,
            (code, f"Default monthly hours benchmark for {name}", code),
        )

    # Roles & Users
    print(f"  -> Ensuring PRISM admin users (Default password: {DEFAULT_PRISM_PASSWORD})...")
    cur.execute("SELECT id FROM roles WHERE name = 'ADMIN';")
    r = cur.fetchone()
    if not r:
        cur.execute("INSERT INTO roles (name, description) VALUES ('ADMIN', 'Full system administrator') RETURNING id;")
        admin_role_id = cur.fetchone()[0]
    else:
        admin_role_id = r[0]

    prism_pw_hash = prism_hash_password(DEFAULT_PRISM_PASSWORD)

    for email, full_name in PRISM_ADMINS:
        cur.execute("SELECT id FROM users WHERE email = %s;", (email,))
        u = cur.fetchone()
        if not u:
            cur.execute(
                """
                INSERT INTO users (email, full_name, hashed_password, is_active)
                VALUES (%s, %s, %s, TRUE)
                RETURNING id;
                """,
                (email, full_name, prism_pw_hash),
            )
            u_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s) ON CONFLICT DO NOTHING;",
                (u_id, admin_role_id),
            )
        else:
            u_id = u[0]
            cur.execute(
                "UPDATE users SET hashed_password = %s, full_name = %s, is_active = TRUE WHERE id = %s;",
                (prism_pw_hash, full_name, u_id),
            )
            cur.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s) ON CONFLICT DO NOTHING;",
                (u_id, admin_role_id),
            )

    # Nashik Incentive Slabs (All slabs)
    print("  -> Ensuring PRISM Nashik calculation slabs...")
    for low, high, amt in NASHIK_SLABS:
        cur.execute(
            """
            INSERT INTO incentive_slabs (
                division, slab_type, role, margin_min, margin_max, amount, effective_from, is_active
            )
            SELECT 'nashik', 'MARGIN', 'RECRUITER', %s, %s, %s, '2024-01-01', TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM incentive_slabs 
                WHERE division = 'nashik' AND role = 'RECRUITER' AND margin_min = %s AND margin_max = %s
            );
            """,
            (low, high, amt, low, high),
        )

    # 5. Sample Candidates for Testing Cycles
    candidates = []
    for ext_id, cname, sdate, ctype, source, org, margin, rec, mgr, div in candidates:
        pass

    cur.close()
    print("  [OK] PRISM seeding completed successfully.")


# ==============================================================================
# MAIN ENTRYPOINT
# ==============================================================================

def print_credentials_summary():
    print("\n" + "=" * 70)
    print(" SEED DATA POPULATED SUCCESSFULLY - READY FOR TESTING")
    print("=" * 70)
    print("\n1. STARTS MIS (New Starts Portal)")
    print(f"   Default Password for all test users: '{DEFAULT_MIS_PASSWORD}'")
    print("   ---------------------------------------------------------------")
    print(f"   {'Role':<22} | {'Email':<28} | {'Full Name'}")
    print("   ---------------------------------------------------------------")
    for u in USERS:
        print(f"   {u['role']:<22} | {u['email']:<28} | {u['full_name']}")

    print("\n2. PRISM (Incentive Tracker Portal)")
    print(f"   Default Password for PRISM users: '{DEFAULT_PRISM_PASSWORD}'")
    print("   ---------------------------------------------------------------")
    print(f"   {'Role':<22} | {'Email':<26} | {'Full Name'}")
    print("   ---------------------------------------------------------------")
    print(f"   {'Admin':<22} | {'admin@example.com':<26} | Default Admin")
    

    print("\n3. API & Web UI URLs")
    print("   Backend API:   http://localhost:8000")
    print("   Swagger Docs:  http://localhost:8000/docs")
    print("   Health Check:  http://localhost:8000/health")
    print("   Frontend App:  http://localhost:5173 (or :8080)")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Seed test users and data for MIS and PRISM.")
    parser.add_argument("--mis-only", action="store_true", help="Seed only Starts MIS data")
    parser.add_argument("--prism-only", action="store_true", help="Seed only PRISM data")
    parser.add_argument("--reset-passwords", action="store_true", help="Reset all test user passwords to defaults")
    parser.add_argument("--db-name", type=str, default=None, help="Override database name")
    args = parser.parse_args()

    conn = get_connection(db_name=args.db_name)

    if not args.prism_only:
        seed_mis(conn, reset_passwords=args.reset_passwords)

    if not args.mis_only:
        seed_prism(conn, reset_passwords=args.reset_passwords)

    conn.close()
    print_credentials_summary()


if __name__ == "__main__":
    main()
