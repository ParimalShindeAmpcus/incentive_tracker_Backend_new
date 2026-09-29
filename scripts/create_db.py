"""
Unified Database & Tables Creation Script for Starts MIS & PRISM Platform.

This single standalone script:
  1. Ensures the target PostgreSQL database (default: 'mis_prism_db') exists.
  2. Configures schemas ('mis', 'prism', 'public') and extensions ('citext').
  3. Creates all tables, enums, sequences, and indexes for Starts MIS in schema 'mis'.
  4. Creates all tables, views, and indexes for PRISM in schema 'prism'.
  5. Stamps alembic_version in schema 'mis' to support future migrations.

Usage:
    python scripts/create_db.py
    python scripts/create_db.py --reset    # Drop and recreate schemas (fresh start)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    from sqlalchemy import text
    from mis.core.config import settings as mis_settings
    from prism.config import get_settings as get_prism_settings
    from prism.core.db import get_engine as get_prism_engine, init_db as init_prism_db
except ImportError as e:
    print(f"\n[ERROR] Missing required dependency: {e}")
    print("[TIP] Please run with your virtual environment:")
    print("      .\\venv\\Scripts\\python.exe create_db.py")
    print("      or activate it first: .\\venv\\Scripts\\activate\n")
    sys.exit(1)


MIS_SCHEMA_DDL = """
-- Citext extension in public schema
CREATE EXTENSION IF NOT EXISTS citext SCHEMA public;

-- Enums in mis schema
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'submission_status') THEN
        CREATE TYPE submission_status AS ENUM (
            'IMPORTED', 'DRAFT', 'SUBMITTED', 'MANAGER_REVIEW',
            'ONBOARDING_REVIEW', 'MIS_REVIEW', 'APPROVED', 'REJECTED', 'COMPLETED'
        );
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'approval_action') THEN
        CREATE TYPE approval_action AS ENUM (
            'SUBMIT', 'APPROVE', 'REJECT', 'REQUEST_CHANGES', 'REOPEN'
        );
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'incentive_status') THEN
        CREATE TYPE incentive_status AS ENUM (
            'CALCULATED', 'PENDING_APPROVAL', 'APPROVED', 'PAID', 'ADJUSTED', 'VOID'
        );
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'audit_action') THEN
        CREATE TYPE audit_action AS ENUM (
            'CREATE', 'UPDATE', 'DELETE', 'STATUS_CHANGE', 'LOGIN', 'EXPORT', 'IMPORT'
        );
    END IF;
END $$;

-- Organizations
CREATE TABLE IF NOT EXISTS organizations (
    id              BIGSERIAL PRIMARY KEY,
    code            VARCHAR(20)  NOT NULL UNIQUE,
    name            VARCHAR(150) NOT NULL,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_by      BIGINT,
    updated_by      BIGINT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ  NULL
);

-- Roles
CREATE TABLE IF NOT EXISTS roles (
    id    SMALLSERIAL PRIMARY KEY,
    code  VARCHAR(20) NOT NULL UNIQUE,
    name  VARCHAR(50) NOT NULL
);

-- Onboarding Organizations
CREATE TABLE IF NOT EXISTS onboarding_organizations (
    id           BIGSERIAL PRIMARY KEY,
    code         VARCHAR(50)  NOT NULL UNIQUE,
    name         VARCHAR(150) NOT NULL,
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    created_by   BIGINT,
    updated_by   BIGINT,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    deleted_at   TIMESTAMPTZ
);

-- Users
CREATE TABLE IF NOT EXISTS users (
    id                          BIGSERIAL PRIMARY KEY,
    organization_id             BIGINT       NOT NULL REFERENCES organizations(id),
    role_id                     SMALLINT     NOT NULL REFERENCES roles(id),
    onboarding_organization_id  BIGINT       REFERENCES onboarding_organizations(id),
    employee_code               VARCHAR(50)  UNIQUE,
    full_name                   VARCHAR(150) NOT NULL,
    email                       CITEXT       NOT NULL UNIQUE,
    password_hash               VARCHAR(255) NULL,
    azure_oid                   VARCHAR(64)  UNIQUE,
    team_name                   VARCHAR(100),
    phone                       VARCHAR(30),
    location                    VARCHAR(150),
    is_active                   BOOLEAN      NOT NULL DEFAULT TRUE,
    is_super_admin              BOOLEAN      NOT NULL DEFAULT FALSE,
    last_login_at               TIMESTAMPTZ,
    created_by                  BIGINT REFERENCES users(id),
    updated_by                  BIGINT REFERENCES users(id),
    created_at                  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    deleted_at                  TIMESTAMPTZ  NULL
);

CREATE INDEX IF NOT EXISTS ix_users_org_role ON users(organization_id, role_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_users_onboarding_org ON users(onboarding_organization_id) WHERE deleted_at IS NULL AND onboarding_organization_id IS NOT NULL;

-- Onboarding Organization Mappings
CREATE TABLE IF NOT EXISTS onboarding_organization_mappings (
    id                          BIGSERIAL PRIMARY KEY,
    onboarding_organization_id  BIGINT NOT NULL REFERENCES onboarding_organizations(id),
    organization_id             BIGINT NOT NULL REFERENCES organizations(id),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (onboarding_organization_id, organization_id)
);

CREATE INDEX IF NOT EXISTS ix_onboard_org_map_onboard ON onboarding_organization_mappings(onboarding_organization_id);
CREATE INDEX IF NOT EXISTS ix_onboard_org_map_org ON onboarding_organization_mappings(organization_id);

-- Recruiter-Manager Mapping
CREATE TABLE IF NOT EXISTS recruiter_manager_mapping (
    id               BIGSERIAL PRIMARY KEY,
    recruiter_id     BIGINT      NOT NULL REFERENCES users(id),
    manager_id       BIGINT      NOT NULL REFERENCES users(id),
    organization_id  BIGINT      NOT NULL REFERENCES organizations(id),
    is_active        BOOLEAN     NOT NULL DEFAULT TRUE,
    effective_from   TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_to     TIMESTAMPTZ NULL,
    created_by       BIGINT REFERENCES users(id),
    updated_by       BIGINT REFERENCES users(id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_recruiter_active_mapping
    ON recruiter_manager_mapping(recruiter_id)
    WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS ix_mapping_manager ON recruiter_manager_mapping(manager_id);

-- Email Import Logs
CREATE TABLE IF NOT EXISTS email_import_logs (
    id               BIGSERIAL PRIMARY KEY,
    run_started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_completed_at TIMESTAMPTZ,
    mailbox          VARCHAR(150),
    message_subject  VARCHAR(255),
    attachment_name  VARCHAR(255),
    total_rows       INTEGER,
    inserted_rows    INTEGER,
    duplicate_rows   INTEGER,
    failed_rows      INTEGER,
    error_detail     TEXT,
    status           VARCHAR(20) NOT NULL DEFAULT 'RUNNING'
);

CREATE INDEX IF NOT EXISTS ix_email_import_status ON email_import_logs(status, run_started_at);

-- Imported JobDiva Records
CREATE TABLE IF NOT EXISTS imported_jobdiva_records (
    id                       BIGSERIAL PRIMARY KEY,
    activity_id              VARCHAR(50)  NOT NULL UNIQUE,
    position_type            VARCHAR(100),
    candidate_full_name      VARCHAR(150),
    candidate_email          VARCHAR(150),
    candidate_city           VARCHAR(100),
    candidate_state          VARCHAR(100),
    candidate_mobile_phone   VARCHAR(30),
    job_company              VARCHAR(150),
    activity_date            DATE,
    jobdiva_ref_no           VARCHAR(100),
    recruited_by             VARCHAR(150),
    recruiter_email          VARCHAR(150),
    job_title                VARCHAR(150),
    work_city                VARCHAR(100),
    work_state               VARCHAR(100),
    start_date               DATE,
    end_date                 DATE,
    end_client_name          VARCHAR(150),
    work_authorization       VARCHAR(100),
    organization_id          BIGINT REFERENCES organizations(id),
    import_batch_id          BIGINT REFERENCES email_import_logs(id),
    raw_row_json             JSONB,
    is_consumed              BOOLEAN NOT NULL DEFAULT FALSE,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_import_org ON imported_jobdiva_records(organization_id);
CREATE INDEX IF NOT EXISTS ix_import_consumed ON imported_jobdiva_records(is_consumed);
CREATE INDEX IF NOT EXISTS ix_import_activity_date ON imported_jobdiva_records(activity_date);

-- Subcontractors
CREATE TABLE IF NOT EXISTS subcontractors (
    id               BIGSERIAL PRIMARY KEY,
    organization_id  BIGINT REFERENCES organizations(id),
    name             VARCHAR(150) NOT NULL,
    email            VARCHAR(150),
    contact_phone    VARCHAR(30),
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_by       BIGINT REFERENCES users(id),
    updated_by       BIGINT REFERENCES users(id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at       TIMESTAMPTZ NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_subcontractor_name_org
    ON subcontractors(name, COALESCE(organization_id, 0))
    WHERE deleted_at IS NULL;

-- Candidate Start
CREATE TABLE IF NOT EXISTS candidate_start (
    id                          BIGSERIAL PRIMARY KEY,
    imported_record_id          BIGINT REFERENCES imported_jobdiva_records(id),
    activity_id                 VARCHAR(50) NOT NULL,
    organization_id             BIGINT NOT NULL REFERENCES organizations(id),
    recruiter_id                BIGINT NOT NULL REFERENCES users(id),
    mapped_manager_id           BIGINT REFERENCES users(id),
    submission_manager_id       BIGINT REFERENCES users(id),

    candidate_name              VARCHAR(150),
    candidate_email             VARCHAR(150),
    candidate_contact_no        VARCHAR(30),
    start_date                  DATE,
    end_date                    DATE,
    client_name                 VARCHAR(150),
    end_client_name             VARCHAR(150),
    contract_type               VARCHAR(50),
    sub_contractor_company      VARCHAR(150),
    sub_contractor_email        VARCHAR(150),
    sub_contractor_contact      VARCHAR(30),
    req_id                      VARCHAR(100),
    job_title                   VARCHAR(150),
    job_level                   VARCHAR(50),
    salary                      NUMERIC(15,3),
    pay_rate                    NUMERIC(15,3),
    taxes                       NUMERIC(15,3),
    benefits                    NUMERIC(15,3),
    referral_fee                NUMERIC(15,3),
    gross_bill_rate             NUMERIC(15,3),
    msp_fee                     NUMERIC(15,3),
    margin                      NUMERIC(15,3),
    margin_is_overridden        BOOLEAN NOT NULL DEFAULT FALSE,
    remote_position             BOOLEAN,
    work_location               VARCHAR(150),
    candidate_location          VARCHAR(150),
    work_authorization          VARCHAR(100),
    resume_source               VARCHAR(100),

    team_lead                   VARCHAR(150),
    crm                         VARCHAR(150),
    team_manager                VARCHAR(150),
    head_of_department          VARCHAR(150),
    senior_manager              VARCHAR(150),
    associate_director          VARCHAR(150),
    director                    VARCHAR(150),
    center_head                 VARCHAR(150),
    assistant_vice_president    VARCHAR(150),
    onboarding_coordinator      VARCHAR(150),

    user_email                  VARCHAR(150),
    recruiter_location          VARCHAR(150),

    status                      submission_status NOT NULL DEFAULT 'IMPORTED',
    version                     INTEGER NOT NULL DEFAULT 1,
    is_deleted                  BOOLEAN NOT NULL DEFAULT FALSE,
    created_by                  BIGINT REFERENCES users(id),
    updated_by                  BIGINT REFERENCES users(id),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_sub_activity_id ON candidate_start(activity_id);
CREATE INDEX IF NOT EXISTS ix_sub_org_status ON candidate_start(organization_id, status) WHERE is_deleted = FALSE;
CREATE INDEX IF NOT EXISTS ix_sub_recruiter ON candidate_start(recruiter_id);
CREATE INDEX IF NOT EXISTS ix_sub_mapped_mgr ON candidate_start(mapped_manager_id);
CREATE INDEX IF NOT EXISTS ix_sub_submission_mgr ON candidate_start(submission_manager_id);
CREATE INDEX IF NOT EXISTS ix_sub_created_at ON candidate_start(created_at);
CREATE INDEX IF NOT EXISTS ix_sub_client_name ON candidate_start(client_name);
CREATE INDEX IF NOT EXISTS ix_sub_manager_visibility ON candidate_start(mapped_manager_id, submission_manager_id, status);

-- Incentives
CREATE TABLE IF NOT EXISTS incentives (
    id                   BIGSERIAL PRIMARY KEY,
    candidate_start_id   BIGINT NOT NULL REFERENCES candidate_start(id),
    organization_id      BIGINT NOT NULL REFERENCES organizations(id),
    recruiter_id         BIGINT NOT NULL REFERENCES users(id),
    manager_id           BIGINT REFERENCES users(id),
    margin_snapshot      NUMERIC(14,2) NOT NULL,
    incentive_amount     NUMERIC(14,2) NOT NULL,
    incentive_percent    NUMERIC(8,4),
    currency_code        CHAR(3) NOT NULL DEFAULT 'USD',
    period_year          SMALLINT NOT NULL,
    period_month         SMALLINT NOT NULL CHECK (period_month BETWEEN 1 AND 12),
    status               incentive_status NOT NULL DEFAULT 'CALCULATED',
    paid_at              TIMESTAMPTZ,
    notes                TEXT,
    version              INTEGER NOT NULL DEFAULT 1,
    created_by           BIGINT REFERENCES users(id),
    updated_by           BIGINT REFERENCES users(id),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_incentive_recruiter ON incentives(recruiter_id, period_year, period_month);
CREATE INDEX IF NOT EXISTS ix_incentive_start ON incentives(candidate_start_id);
CREATE INDEX IF NOT EXISTS ix_incentive_status ON incentives(status);

-- Approvals
CREATE TABLE IF NOT EXISTS approvals (
    id                 BIGSERIAL PRIMARY KEY,
    candidate_start_id BIGINT NOT NULL REFERENCES candidate_start(id),
    incentive_id       BIGINT REFERENCES incentives(id),
    action             approval_action NOT NULL,
    from_status        submission_status,
    to_status          submission_status,
    actor_id           BIGINT NOT NULL REFERENCES users(id),
    comments           TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_approvals_start ON approvals(candidate_start_id, created_at DESC);

-- Audit Logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id               BIGSERIAL PRIMARY KEY,
    organization_id  BIGINT REFERENCES organizations(id),
    actor_id         BIGINT REFERENCES users(id),
    entity_type      VARCHAR(50) NOT NULL,
    entity_id        BIGINT,
    action           audit_action NOT NULL,
    before_json      JSONB,
    after_json       JSONB,
    ip_address       VARCHAR(45),
    user_agent       TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_audit_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS ix_audit_actor ON audit_logs(actor_id, created_at DESC);

-- Dropdown Master
CREATE TABLE IF NOT EXISTS dropdown_master (
    id               BIGSERIAL PRIMARY KEY,
    category         VARCHAR(100) NOT NULL,
    value            VARCHAR(150) NOT NULL,
    display_order    INTEGER DEFAULT 0,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    organization_id  BIGINT REFERENCES organizations(id),
    created_by       BIGINT REFERENCES users(id),
    updated_by       BIGINT REFERENCES users(id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_dropdown_cat_val_org
    ON dropdown_master(category, value, COALESCE(organization_id, 0));

-- Email Templates
CREATE TABLE IF NOT EXISTS email_templates (
    id               BIGSERIAL PRIMARY KEY,
    organization_id  BIGINT REFERENCES organizations(id),
    code             VARCHAR(50) NOT NULL,
    name             VARCHAR(150) NOT NULL,
    subject          VARCHAR(255) NOT NULL,
    body_html        TEXT NOT NULL,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_by       BIGINT REFERENCES users(id),
    updated_by       BIGINT REFERENCES users(id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_email_template_code_org
    ON email_templates(code, COALESCE(organization_id, 0));

-- App Settings
CREATE TABLE IF NOT EXISTS app_settings (
    id               BIGSERIAL PRIMARY KEY,
    organization_id  BIGINT NOT NULL REFERENCES organizations(id),
    key              VARCHAR(100) NOT NULL,
    value_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_by       BIGINT REFERENCES users(id),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (organization_id, key)
);

-- Password Reset Tokens
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_token_hash ON password_reset_tokens (token_hash);
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user_id ON password_reset_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_expires_at ON password_reset_tokens (expires_at);

-- Notifications
CREATE TABLE IF NOT EXISTS notifications (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    candidate_start_id BIGINT REFERENCES candidate_start(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_notifications_user_created ON notifications(user_id, created_at DESC);

-- Alembic Version (stamped with head revision so migrations stay in sync)
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL PRIMARY KEY
);

INSERT INTO alembic_version (version_num)
SELECT 'e9a4d1979cab'
WHERE NOT EXISTS (SELECT 1 FROM alembic_version);
"""

PRISM_VIEWS_DDL = """
-- Master Reports View
CREATE OR REPLACE VIEW master_reports_view AS
SELECT
    il.id AS line_id,
    il.person AS person,
    il.role AS role,
    il.candidate_name AS line_candidate_name,
    il.amount AS amount,
    il.hours AS hours,
    il.margin AS line_margin,
    il.incentive_type AS incentive_type,
    il.eligible AS eligible,
    
    ic.id AS cycle_id,
    ic.name AS cycle_name,
    ic.division AS division,
    ic.incentive_month AS incentive_month,
    ic.status AS cycle_status,
    
    c.external_candidate_id AS external_candidate_id,
    c.candidate_name AS candidate_name,
    c.start_date AS start_date,
    c.contract_type AS contract_type,
    c.candidate_source AS candidate_source,
    c.organization AS organization,
    c.margin AS candidate_margin,
    c.crm AS crm,
    c.center_head AS center_head,
    c.associate_director AS associate_director,
    c.manager AS manager,
    c.senior_manager AS senior_manager,
    c.team_lead AS team_lead
FROM incentive_lines il
JOIN incentive_cycles ic ON ic.id = il.cycle_id
LEFT JOIN candidates c ON c.id = il.candidate_id;
"""


def ensure_database_exists(host: str, port: int, user: str, password: str, db_name: str) -> None:
    """Connect to postgres administrative database and create db_name if missing."""
    conn = psycopg2.connect(host=host, port=port, user=user, password=password, dbname="postgres")
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (db_name,))
    if not cur.fetchone():
        print(f"Creating database '{db_name}'...")
        cur.execute(f'CREATE DATABASE "{db_name}";')
        print(f"Database '{db_name}' created successfully.")
    else:
        print(f"Database '{db_name}' already exists.")
    cur.close()
    conn.close()


def setup_database(reset: bool = False, db_name: str | None = None) -> None:
    """Create schemas, extensions, and tables for both Starts MIS and PRISM."""
    p_settings = get_prism_settings()
    host = mis_settings.DB_HOST
    port = mis_settings.PORT
    user = mis_settings.DB_USER
    password = mis_settings.PASSWORD
    target_db = db_name or mis_settings.DB_NAME or "mis_prism_db"

    print("=================================================================")
    print(f" UNIFIED DATABASE INITIALIZATION: '{target_db}'")
    print("=================================================================")
    ensure_database_exists(host=host, port=port, user=user, password=password, db_name=target_db)

    # 1. Connect to target database
    conn = psycopg2.connect(host=host, port=port, user=user, password=password, dbname=target_db)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    if reset:
        print("\n[RESET] Dropping existing 'mis' and 'prism' schemas...")
        cur.execute("DROP SCHEMA IF EXISTS mis CASCADE;")
        cur.execute("DROP SCHEMA IF EXISTS prism CASCADE;")
        print("[RESET] Schemas dropped.")

    print("\n[1/3] Ensuring schemas and extensions...")
    cur.execute("CREATE EXTENSION IF NOT EXISTS citext SCHEMA public;")
    cur.execute("CREATE SCHEMA IF NOT EXISTS mis;")
    cur.execute("CREATE SCHEMA IF NOT EXISTS prism;")
    cur.execute(f"GRANT ALL ON SCHEMA mis TO {user};")
    cur.execute(f"GRANT ALL ON SCHEMA prism TO {user};")

    print("\n[2/3] Creating Starts MIS tables in schema 'mis'...")
    cur.execute("SET search_path = mis, public;")
    cur.execute(MIS_SCHEMA_DDL)
    print("  -> Starts MIS tables, enums, indexes, and alembic stamp created.")
    cur.close()
    conn.close()

    print("\n[3/3] Creating PRISM tables and views in schema 'prism'...")
    # Initialize PRISM tables via SQLAlchemy Base.metadata.create_all
    init_prism_db()

    # Create views in prism schema
    p_engine = get_prism_engine()
    with p_engine.begin() as p_conn:
        p_conn.execute(text("SET search_path = prism, public;"))
        p_conn.execute(text(PRISM_VIEWS_DDL))
    print("  -> PRISM tables, views, and benchmarks initialized.")

    # 4. Verification
    print("\nVerifying database tables...")
    conn_verify = psycopg2.connect(host=host, port=port, user=user, password=password, dbname=target_db)
    cur_v = conn_verify.cursor()
    for schema_name in ["mis", "prism"]:
        cur_v.execute(
            """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
            ORDER BY table_name;
            """,
            (schema_name,),
        )
        tables = [r[0] for r in cur_v.fetchall()]
        print(f"  Schema '{schema_name}': {len(tables)} tables ready.")
    conn_verify.close()

    print("\n=================================================================")
    print(" DATABASE SETUP COMPLETED SUCCESSFULLY!")
    print(" Next step: Run 'python scripts/seed_data.py' to populate test users.")
    print("=================================================================")


def main():
    parser = argparse.ArgumentParser(description="Create standalone database and tables for MIS and PRISM.")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate schemas (destructive)")
    parser.add_argument("--db-name", type=str, default=None, help="Override database name")
    args = parser.parse_args()

    setup_database(reset=args.reset, db_name=args.db_name)


if __name__ == "__main__":
    main()
