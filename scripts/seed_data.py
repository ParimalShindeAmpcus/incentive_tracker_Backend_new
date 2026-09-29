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



DEFAULT_MIS_PASSWORD = "Password@123"
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
    ("HOD", "Head of Department"),
    ("ONBOARD_TEAM", "Onboarding Team"),
    ("TEAM_LEAD", "Team Lead"),
    ("CRM", "CRM"),
    ("SENIOR_MANAGER", "Senior Manager"),
    ("ASSOCIATE_DIRECTOR", "Associate Director"),
    ("DIRECTOR", "Director"),
    ("CENTER_HEAD", "Center Head"),
    ("AVP", "Assistant Vice President"),
]

MIS_ORGANIZATIONS = [
    ("AMPCUS_INC", "Ampcus Inc"),
    ("AMPCUS_TECH", "Ampcus Tech"),
    ("AMPCUS_CYBER", "Ampcus Cyber"),
    ("BRAVENS_INC", "Bravens Inc"),
    ("APOKRIN_LLC", "Apokrin LLC"),
    ("ITECH_INC", "ITech Inc"),
    ("DEFAULT", "Default Organization"),
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
    # ORGANIZATION
    ("ORGANIZATION", "Ampcus Inc", 1),
    ("ORGANIZATION", "Ampcus Tech", 2),
    ("ORGANIZATION", "Ampcus Cyber", 3),
    ("ORGANIZATION", "Bravens Inc", 4),
    ("ORGANIZATION", "Apokrin LLC", 5),
    ("ORGANIZATION", "ITech Inc", 6),
    # CURRENCY
    ("CURRENCY", "USD", 1),
    ("CURRENCY", "CAD", 2),
    ("CURRENCY", "INR", 3),
    # JOB_LEVEL
    ("JOB_LEVEL", "Junior", 1),
    ("JOB_LEVEL", "Mid-Level", 2),
    ("JOB_LEVEL", "Senior", 3),
    ("JOB_LEVEL", "Lead", 4),
    ("JOB_LEVEL", "Architect", 5),
    # TAXES_ADMIN_PAYROLL_CHARGES
    ("TAXES_ADMIN_PAYROLL_CHARGES", "0", 1),
    ("TAXES_ADMIN_PAYROLL_CHARGES", "5", 2),
    ("TAXES_ADMIN_PAYROLL_CHARGES", "15.4", 3),
    ("TAXES_ADMIN_PAYROLL_CHARGES", "20.4", 4),
]

MIS_TEST_USERS = [
    # (email, full_name, role_code, org_code, emp_code)
    ("admin1@bravens.com", "Deepak Kumar", "MIS", "BRAVENS_INC", "EMP-001"),
    ("admin2@bravens.com", "Meera Iyer", "MIS", "BRAVENS_INC", "EMP-002"),
    ("admin@bravens.com", "System Admin", "MIS", "BRAVENS_INC", "EMP-003"),
    ("mis.admin@ampcus.com", "Ampcus MIS Admin", "MIS", "AMPCUS_INC", "EMP-004"),
    ("manager1@bravens.com", "Karan Malhotra", "MANAGER", "BRAVENS_INC", "EMP-010"),
    ("manager2@bravens.com", "Pooja Reddy", "MANAGER", "BRAVENS_INC", "EMP-011"),
    ("manager@ampcus.com", "Ampcus Manager", "MANAGER", "AMPCUS_INC", "EMP-012"),
    ("recruiter1@bravens.com", "Arjun Singh", "RECRUITER", "BRAVENS_INC", "EMP-020"),
    ("recruiter2@bravens.com", "Neha Patel", "RECRUITER", "BRAVENS_INC", "EMP-021"),
    ("recruiter@ampcus.com", "Ampcus Recruiter", "RECRUITER", "AMPCUS_INC", "EMP-022"),
    ("b.ampcus@gmail.com", "Bhushan Chitte", "RECRUITER", "AMPCUS_INC", "EMP-023"),
    ("hod1@bravens.com", "Sanjay Mehta", "HOD", "BRAVENS_INC", "EMP-030"),
    ("hod@ampcus.com", "Ampcus HOD", "HOD", "AMPCUS_INC", "EMP-031"),
    ("onboarding1@bravens.com", "Sneha Nair", "ONBOARD_TEAM", "BRAVENS_INC", "EMP-040"),
    ("onboarding2@bravens.com", "Rahul Verma", "ONBOARD_TEAM", "BRAVENS_INC", "EMP-041"),
    ("teamlead1@bravens.com", "Vivek Chauhan", "TEAM_LEAD", "BRAVENS_INC", "EMP-050"),
    ("teamlead@ampcus.com", "Ampcus Team Lead", "TEAM_LEAD", "AMPCUS_INC", "EMP-051"),
    ("crm1@bravens.com", "Manoj Tiwari", "CRM", "BRAVENS_INC", "EMP-060"),
    ("seniormanager1@bravens.com", "Rajesh Khanna", "SENIOR_MANAGER", "BRAVENS_INC", "EMP-070"),
    ("associatedirector1@bravens.com", "Ashwin Menon", "ASSOCIATE_DIRECTOR", "BRAVENS_INC", "EMP-080"),
    ("director1@bravens.com", "Nikhil Bansal", "DIRECTOR", "BRAVENS_INC", "EMP-090"),
    ("centerhead1@bravens.com", "Suresh Pillai", "CENTER_HEAD", "BRAVENS_INC", "EMP-100"),
    ("avp1@bravens.com", "Harsh Vardhan", "AVP", "BRAVENS_INC", "EMP-110"),
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

    # 5. Users
    print(f"  -> Seeding MIS test users (Default password: {DEFAULT_MIS_PASSWORD})...")
    default_pw_hash = mis_hash_password(DEFAULT_MIS_PASSWORD)
    user_ids = {}

    for email, full_name, role_code, org_code, emp_code in MIS_TEST_USERS:
        oid = org_ids.get(org_code, org_ids["BRAVENS_INC"])
        rid = role_ids.get(role_code, role_ids["RECRUITER"])
        onboard_id = ampcus_onboard_id if "ampcus" in org_code.lower() else bravens_onboard_id

        cur.execute("SELECT id, password_hash FROM users WHERE email = %s;", (email,))
        row = cur.fetchone()
        if not row:
            cur.execute(
                """
                INSERT INTO users (
                    organization_id, role_id, onboarding_organization_id,
                    employee_code, full_name, email, password_hash, is_active, is_super_admin
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, %s)
                RETURNING id;
                """,
                (oid, rid, onboard_id, emp_code, full_name, email, default_pw_hash, role_code == "MIS"),
            )
            user_ids[email] = cur.fetchone()[0]
        else:
            user_ids[email] = row[0]
            if reset_passwords:
                cur.execute("UPDATE users SET password_hash = %s WHERE id = %s;", (default_pw_hash, row[0]))

    # 6. Recruiter-Manager Mapping
    print("  -> Seeding recruiter-manager mappings...")
    mgr1_id = user_ids.get("manager1@bravens.com")
    rec1_id = user_ids.get("recruiter1@bravens.com")
    bhushan_id = user_ids.get("b.ampcus@gmail.com")
    ampcus_mgr_id = user_ids.get("manager@ampcus.com")
    ampcus_rec_id = user_ids.get("recruiter@ampcus.com")

    mappings = [
        (rec1_id, mgr1_id, org_ids["BRAVENS_INC"]),
        (bhushan_id, mgr1_id, org_ids["BRAVENS_INC"]),
        (ampcus_rec_id, ampcus_mgr_id, org_ids["AMPCUS_INC"]),
    ]
    for r_id, m_id, o_id in mappings:
        if r_id and m_id:
            cur.execute(
                """
                INSERT INTO recruiter_manager_mapping (recruiter_id, manager_id, organization_id, is_active)
                SELECT %s, %s, %s, TRUE
                WHERE NOT EXISTS (
                    SELECT 1 FROM recruiter_manager_mapping WHERE recruiter_id = %s AND is_active = TRUE
                );
                """,
                (r_id, m_id, o_id, r_id),
            )

    # 7. Sample Starts (Submissions)
    print("  -> Seeding sample candidate starts...")
    sample_starts = [
        (
            "ACT-JOB-001",
            "David Miller",
            "david.miller@example.com",
            "W2",
            "Apple Inc",
            "Apple Inc",
            "Software Engineer",
            date(2026, 6, 15),
            Decimal("65.00"),
            Decimal("85.00"),
            Decimal("18.50"),
            "DRAFT",
            rec1_id,
            mgr1_id,
        ),
        (
            "ACT-JOB-002",
            "Sarah Connor",
            "sarah.c@example.com",
            "C2C",
            "Google LLC",
            "Alphabet",
            "Cloud Architect",
            date(2026, 7, 1),
            Decimal("75.00"),
            Decimal("105.00"),
            Decimal("24.00"),
            "SUBMITTED",
            rec1_id,
            mgr1_id,
        ),
        (
            "ACT-JOB-003",
            "Michael Scott",
            "michael.s@example.com",
            "W2",
            "Microsoft",
            "Microsoft Corp",
            "DevOps Engineer",
            date(2026, 8, 1),
            Decimal("70.00"),
            Decimal("96.50"),
            Decimal("22.50"),
            "MANAGER_REVIEW",
            bhushan_id or rec1_id,
            mgr1_id,
        ),
        (
            "ACT-JOB-004",
            "Emily Watson",
            "emily.w@example.com",
            "FTE",
            "Amazon",
            "AWS",
            "Data Scientist",
            date(2026, 8, 15),
            Decimal("80.00"),
            Decimal("120.00"),
            Decimal("35.00"),
            "APPROVED",
            rec1_id,
            mgr1_id,
        ),
    ]

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
                    organization_id, is_consumed
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)
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
                    org_ids["BRAVENS_INC"],
                ),
            )
            imported_id = cur.fetchone()[0]
        else:
            imported_id = job_row[0]

        # 2. Insert candidate start
        cur.execute("SELECT id FROM candidate_start WHERE activity_id = %s;", (act_id,))
        if not cur.fetchone():
            cur.execute(
                """
                INSERT INTO candidate_start (
                    imported_record_id, activity_id, organization_id, recruiter_id,
                    mapped_manager_id, submission_manager_id,
                    candidate_name, candidate_email, contract_type, client_name, end_client_name,
                    job_title, start_date, pay_rate, gross_bill_rate, margin, status
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                );
                """,
                (
                    imported_id,
                    act_id,
                    org_ids["BRAVENS_INC"],
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
                ),
            )

    cur.close()
    print("  [OK] Starts MIS seeding completed successfully.")


# ==============================================================================
# PART 2: SEED PRISM (Schema: prism)
# ==============================================================================

PRISM_DIVISIONS = [
    ("nashik", "Nashik Division"),
    ("sambhajiNagar", "Sambhaji Nagar Division"),
    ("ampcusTechClient", "Ampcus Tech (Client)"),
    ("ampcusTechInhouse", "Ampcus Tech In-House"),
]

PRISM_ADMINS = [
    ("admin@example.com", "Default Admin"),
    ("priya@ampcustech.com", "Priya"),
    ("abhijeet@ampcustech.com", "Abhijit"),
    ("priya@example.com", "Priya Example"),
    ("abhishek@example.com", "Abhishek Example"),
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
    cur = conn.cursor()
    cur.execute("SET search_path = prism, public;")

    # 1. Organization & Divisions
    print("  -> Seeding PRISM organization and divisions...")
    cur.execute("SELECT id FROM organizations WHERE code = 'DEFAULT';")
    row = cur.fetchone()
    if not row:
        cur.execute(
            "INSERT INTO organizations (code, name) VALUES ('DEFAULT', 'Default Organization') RETURNING id;"
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
                "INSERT INTO divisions (organization_id, code, name) VALUES (%s, %s, %s) RETURNING id;",
                (org_id, code, name),
            )
            div_ids[code] = cur.fetchone()[0]
        else:
            div_ids[code] = r[0]

    # 2. Hours Benchmarks
    print("  -> Seeding PRISM hours benchmarks (160h)...")
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

    # 3. Roles & Users
    print(f"  -> Seeding PRISM admin users (Default password: {DEFAULT_PRISM_PASSWORD})...")
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
            if reset_passwords:
                cur.execute("UPDATE users SET hashed_password = %s WHERE id = %s;", (prism_pw_hash, u_id))
            cur.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s) ON CONFLICT DO NOTHING;",
                (u_id, admin_role_id),
            )

    # 4. Nashik Incentive Slabs
    print("  -> Seeding PRISM Nashik calculation slabs...")
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
    print("  -> Seeding sample PRISM candidates...")
    cur.execute("SELECT id FROM candidate_data_versions ORDER BY id ASC LIMIT 1;")
    v_row = cur.fetchone()
    if not v_row:
        cur.execute(
            """
            INSERT INTO candidate_data_versions (version_label, source_filename, row_count, notes)
            VALUES ('Initial Seed Version', 'seed_candidates.xlsx', 2, 'Initial seed candidates for testing')
            RETURNING id;
            """
        )
        version_id = cur.fetchone()[0]
    else:
        version_id = v_row[0]

    candidates = [
        (
            "CAND-NASHIK-001",
            "John Doe",
            date(2026, 6, 1),
            "W2",
            "JobDiva",
            "Ampcus Inc",
            Decimal("15.00"),
            "Priya",
            "Manager A",
            "nashik",
        ),
        (
            "CAND-INHOUSE-002",
            "Jane Smith",
            date(2026, 7, 1),
            "FTE",
            "LinkedIn",
            "Ampcus Tech",
            Decimal("18.50"),
            "Abhijit",
            "Manager B",
            "ampcusTechInhouse",
        ),
    ]

    for ext_id, cname, sdate, ctype, source, org, margin, rec, mgr, div in candidates:
        cur.execute("SELECT id FROM candidates WHERE external_candidate_id = %s;", (ext_id,))
        if not cur.fetchone():
            cur.execute(
                """
                INSERT INTO candidates (
                    source_version_id, last_touched_version_id, external_candidate_id,
                    candidate_name, normalized_name, start_date, contract_type,
                    candidate_source, organization, margin, recruiter, manager,
                    status, is_active, incentive_active, ownership_confirmed
                ) VALUES (
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    'Active', TRUE, TRUE, TRUE
                );
                """,
                (version_id, version_id, ext_id, cname, cname.strip().lower(), sdate, ctype, source, org, margin, rec, mgr),
            )

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
    print(f"   {'Role':<22} | {'Email':<26} | {'Full Name'}")
    print("   ---------------------------------------------------------------")
    print(f"   {'Admin (MIS)':<22} | {'admin1@bravens.com':<26} | Deepak Kumar")
    print(f"   {'Admin (MIS)':<22} | {'mis.admin@ampcus.com':<26} | Ampcus MIS Admin")
    print(f"   {'Recruiter':<22} | {'recruiter1@bravens.com':<26} | Arjun Singh")
    print(f"   {'Recruiter':<22} | {'b.ampcus@gmail.com':<26} | Bhushan Chitte")
    print(f"   {'Manager':<22} | {'manager1@bravens.com':<26} | Karan Malhotra")
    print(f"   {'HOD':<22} | {'hod1@bravens.com':<26} | Sanjay Mehta")
    print(f"   {'Onboarding Team':<22} | {'onboarding1@bravens.com':<26} | Sneha Nair")
    print(f"   {'Team Lead':<22} | {'teamlead1@bravens.com':<26} | Vivek Chauhan")

    print("\n2. PRISM (Incentive Tracker Portal)")
    print(f"   Default Password for PRISM users: '{DEFAULT_PRISM_PASSWORD}'")
    print("   ---------------------------------------------------------------")
    print(f"   {'Role':<22} | {'Email':<26} | {'Full Name'}")
    print("   ---------------------------------------------------------------")
    print(f"   {'Admin':<22} | {'admin@example.com':<26} | Default Admin")
    print(f"   {'Admin':<22} | {'priya@ampcustech.com':<26} | Priya")
    print(f"   {'Admin':<22} | {'abhijeet@ampcustech.com':<26} | Abhijit")

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
