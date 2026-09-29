-- =========================================================
-- Recruitment MIS / Recruiter Incentive — PostgreSQL Schema
-- Synced with MIS-web frontend + folder-structure entities
-- Extensions required: citext
-- =========================================================

CREATE EXTENSION IF NOT EXISTS citext;

-- =========================================================
-- ENUMS
-- =========================================================
CREATE TYPE submission_status AS ENUM (
    'IMPORTED',
    'DRAFT',
    'SUBMITTED',
    'MANAGER_REVIEW',
    'MIS_REVIEW',
    'APPROVED',
    'REJECTED',
    'COMPLETED'
);

CREATE TYPE approval_action AS ENUM (
    'SUBMIT',
    'APPROVE',
    'REJECT',
    'REQUEST_CHANGES',
    'REOPEN'
);

CREATE TYPE incentive_status AS ENUM (
    'CALCULATED',
    'PENDING_APPROVAL',
    'APPROVED',
    'PAID',
    'ADJUSTED',
    'VOID'
);

CREATE TYPE audit_action AS ENUM (
    'CREATE',
    'UPDATE',
    'DELETE',
    'STATUS_CHANGE',
    'LOGIN',
    'EXPORT',
    'IMPORT'
);

-- =========================================================
-- ORGANIZATIONS
-- =========================================================
CREATE TABLE organizations (
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

-- =========================================================
-- ROLES
-- Only Admin (MIS) role is seeded
-- =========================================================
CREATE TABLE roles (
    id    SMALLSERIAL PRIMARY KEY,
    code  VARCHAR(20) NOT NULL UNIQUE,
    name  VARCHAR(50) NOT NULL
);

INSERT INTO roles (code, name) VALUES
    ('MIS', 'Admin');

-- =========================================================
-- USERS
-- password_hash nullable when Azure AD (MSAL) is sole auth
-- azure_oid added for Entra ID subject mapping
-- =========================================================
CREATE TABLE users (
    id               BIGSERIAL PRIMARY KEY,
    organization_id  BIGINT       NOT NULL REFERENCES organizations(id),
    role_id          SMALLINT     NOT NULL REFERENCES roles(id),
    employee_code    VARCHAR(50)  UNIQUE,
    full_name        VARCHAR(150) NOT NULL,
    email            CITEXT       NOT NULL UNIQUE,
    password_hash    VARCHAR(255) NULL,
    azure_oid        VARCHAR(64)  UNIQUE,
    team_name        VARCHAR(100),
    phone            VARCHAR(30),
    location         VARCHAR(150),
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    is_super_admin   BOOLEAN      NOT NULL DEFAULT FALSE,
    last_login_at    TIMESTAMPTZ,
    created_by       BIGINT REFERENCES users(id),
    updated_by       BIGINT REFERENCES users(id),
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    deleted_at       TIMESTAMPTZ  NULL
);

CREATE INDEX ix_users_org_role ON users(organization_id, role_id) WHERE deleted_at IS NULL;

-- =========================================================
-- RECRUITER <-> MANAGER PERMANENT MAPPING
-- =========================================================
CREATE TABLE recruiter_manager_mapping (
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

CREATE UNIQUE INDEX ux_recruiter_active_mapping
    ON recruiter_manager_mapping(recruiter_id)
    WHERE is_active = TRUE;

CREATE INDEX ix_mapping_manager ON recruiter_manager_mapping(manager_id);

-- =========================================================
-- EMAIL IMPORT LOGS (defined before imported_jobdiva_records)
-- =========================================================
CREATE TABLE email_import_logs (
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

CREATE INDEX ix_email_import_status ON email_import_logs(status, run_started_at);

-- =========================================================
-- IMPORTED JOBDIVA RECORDS
-- =========================================================
CREATE TABLE imported_jobdiva_records (
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

CREATE INDEX ix_import_org ON imported_jobdiva_records(organization_id);
CREATE INDEX ix_import_consumed ON imported_jobdiva_records(is_consumed);
CREATE INDEX ix_import_activity_date ON imported_jobdiva_records(activity_date);

-- =========================================================
-- SUBCONTRACTORS (master directory used by New Start form)
-- =========================================================
CREATE TABLE subcontractors (
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

CREATE UNIQUE INDEX ux_subcontractor_name_org
    ON subcontractors(name, COALESCE(organization_id, 0))
    WHERE deleted_at IS NULL;

-- =========================================================
-- CANDIDATE START (Accounts / recruiter submission)
-- =========================================================
CREATE TABLE candidate_start (
    id                          BIGSERIAL PRIMARY KEY,
    imported_record_id          BIGINT NOT NULL REFERENCES imported_jobdiva_records(id),
    activity_id                 VARCHAR(50) NOT NULL,
    organization_id             BIGINT NOT NULL REFERENCES organizations(id),
    recruiter_id                BIGINT NOT NULL REFERENCES users(id),
    mapped_manager_id           BIGINT REFERENCES users(id),
    submission_manager_id       BIGINT NOT NULL REFERENCES users(id),

    -- Accounts / commercial fields (aligned with New Start form)
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

    -- Hierarchy / incentive chain (display names; IDs optional via users later)
    team_lead                   VARCHAR(150),
    crm                         VARCHAR(150),
    team_manager                VARCHAR(150),
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

CREATE INDEX ix_sub_activity_id ON candidate_start(activity_id);
CREATE INDEX ix_sub_org_status ON candidate_start(organization_id, status) WHERE is_deleted = FALSE;
CREATE INDEX ix_sub_recruiter ON candidate_start(recruiter_id);
CREATE INDEX ix_sub_mapped_mgr ON candidate_start(mapped_manager_id);
CREATE INDEX ix_sub_submission_mgr ON candidate_start(submission_manager_id);
CREATE INDEX ix_sub_created_at ON candidate_start(created_at);
CREATE INDEX ix_sub_client_name ON candidate_start(client_name);
CREATE INDEX ix_sub_manager_visibility
    ON candidate_start(mapped_manager_id, submission_manager_id, status);

-- =========================================================
-- INCENTIVES (frontend /incentives + calculation engine)
-- =========================================================
CREATE TABLE incentives (
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

CREATE INDEX ix_incentive_recruiter ON incentives(recruiter_id, period_year, period_month);
CREATE INDEX ix_incentive_start ON incentives(candidate_start_id);
CREATE INDEX ix_incentive_status ON incentives(status);

-- =========================================================
-- APPROVALS (workflow history for candidate_start / incentives)
-- =========================================================
CREATE TABLE approvals (
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

CREATE INDEX ix_approvals_start ON approvals(candidate_start_id, created_at DESC);

-- =========================================================
-- AUDIT LOGS
-- =========================================================
CREATE TABLE audit_logs (
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

CREATE INDEX ix_audit_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX ix_audit_actor ON audit_logs(actor_id, created_at DESC);

-- =========================================================
-- DROPDOWN MASTER (configurable LOVs)
-- Categories used by frontend New Start + Master Data
-- =========================================================
CREATE TABLE dropdown_master (
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

CREATE UNIQUE INDEX ux_dropdown_cat_val_org
    ON dropdown_master(category, value, COALESCE(organization_id, 0));

-- =========================================================
-- EMAIL TEMPLATES (frontend /email-templates)
-- =========================================================
CREATE TABLE email_templates (
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

CREATE UNIQUE INDEX ux_email_template_code_org
    ON email_templates(code, COALESCE(organization_id, 0));

-- =========================================================
-- APP SETTINGS (frontend /settings)
-- =========================================================
CREATE TABLE app_settings (
    id               BIGSERIAL PRIMARY KEY,
    organization_id  BIGINT NOT NULL REFERENCES organizations(id),
    key              VARCHAR(100) NOT NULL,
    value_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_by       BIGINT REFERENCES users(id),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (organization_id, key)
);

-- =========================================================
-- SEED: dropdown categories aligned with New Start form
-- =========================================================
INSERT INTO dropdown_master (category, value, display_order) VALUES
    ('CONTRACT_TYPE', 'W2', 1),
    ('CONTRACT_TYPE', 'C2C', 2),
    ('CONTRACT_TYPE', 'T4', 3),
    ('CONTRACT_TYPE', 'FTE', 4),
    ('CONTRACT_TYPE', 'SOW', 5),
    ('JOB_LEVEL', 'Junior', 1),
    ('JOB_LEVEL', 'Mid', 2),
    ('JOB_LEVEL', 'Senior', 3),
    ('JOB_LEVEL', 'Lead', 4),
    ('JOB_LEVEL', 'Architect', 5),
    ('JOB_LEVEL', 'Manager', 6),
    ('JOB_LEVEL', 'Director', 7),
    ('JOB_LEVEL', 'NA', 8),
    ('RESUME_SOURCE', 'LinkedIn', 1),
    ('RESUME_SOURCE', 'LinkedIn RPS', 2),
    ('RESUME_SOURCE', 'Dice', 3),
    ('RESUME_SOURCE', 'Monster', 4),
    ('RESUME_SOURCE', 'Indeed', 5),
    ('RESUME_SOURCE', 'CareerBuilder', 6),
    ('RESUME_SOURCE', 'Referral', 7),
    ('RESUME_SOURCE', 'Internal Database', 8),
    ('RESUME_SOURCE', 'Company Website', 9),
    ('RESUME_SOURCE', 'JobDiva', 10),
    ('RESUME_SOURCE', 'Other', 11),
    ('WORK_AUTHORIZATION', 'US Citizen', 1),
    ('WORK_AUTHORIZATION', 'Green Card', 2),
    ('WORK_AUTHORIZATION', 'GC', 3),
    ('WORK_AUTHORIZATION', 'H1B', 4),
    ('WORK_AUTHORIZATION', 'OPT', 5),
    ('WORK_AUTHORIZATION', 'TN', 6),
    ('RECRUITER_LOCATION', 'Nashik', 1),
    ('RECRUITER_LOCATION', 'Pune', 2),
    ('RECRUITER_LOCATION', 'Hyderabad', 3),
    ('RECRUITER_LOCATION', 'Noida', 4),
    ('RECRUITER_LOCATION', 'Remote', 5),
    ('TEAM', 'Alpha', 1),
    ('TEAM', 'Bravo', 2),
    ('TEAM', 'Charlie', 3),
    ('TEAM', 'Delta', 4),
    ('TAXES_ADMIN_PAYROLL_CHARGES', '0', 1),
    ('TAXES_ADMIN_PAYROLL_CHARGES', '5', 2),
    ('TAXES_ADMIN_PAYROLL_CHARGES', '15.4', 3),
    ('TAXES_ADMIN_PAYROLL_CHARGES', '20.4', 4),
    -- Organizations
    ('ORGANIZATION', 'Ampcus Cyber', 1),
    ('ORGANIZATION', 'Ampcus Tech', 2),
    ('ORGANIZATION', 'Ampcus Inc', 3),
    ('ORGANIZATION', 'Ampcus Health', 4),
    ('ORGANIZATION', 'Bravens', 5),
    ('ORGANIZATION', 'Bravens Global', 6),
    ('ORGANIZATION', 'Bravens Technologies', 7),
    ('ORGANIZATION', 'Bravens Inc', 8),
    ('ORGANIZATION', 'ITech Inc', 9),
    ('ORGANIZATION', 'Apokrin LLC', 10),
    ('ORGANIZATION', 'BravensTech', 11);

-- =========================================================
-- SEED: organizations table (mirrors dropdown ORGANIZATION values)
-- =========================================================
INSERT INTO organizations (code, name, is_active) VALUES
    ('AMP_CYBER',      'Ampcus Cyber',        TRUE),
    ('AMP_TECH',       'Ampcus Tech',         TRUE),
    ('AMP_INC',        'Ampcus Inc',          TRUE),
    ('AMP_HEALTH',     'Ampcus Health',       TRUE),
    ('BRAVENS',        'Bravens',             TRUE),
    ('BRAVENS_GLOBAL', 'Bravens Global',      TRUE),
    ('BRAVENS_TECH',   'Bravens Technologies',TRUE),
    ('BRAVENS_INC',    'Bravens Inc',         TRUE),
    ('ITECH',          'ITech Inc',           TRUE),
    ('APOKRIN',        'Apokrin LLC',         TRUE),
    ('BRAVENSTECH',    'BravensTech',         TRUE)
ON CONFLICT (code) DO NOTHING;

