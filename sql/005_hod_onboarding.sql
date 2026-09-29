-- HOD role, Onboarding Team role, onboarding organizations, and multi-stage approval

-- New submission status for onboarding team review
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_enum e
    JOIN pg_type t ON t.oid = e.enumtypid
    WHERE t.typname = 'submission_status' AND e.enumlabel = 'ONBOARDING_REVIEW'
  ) THEN
    ALTER TYPE submission_status ADD VALUE 'ONBOARDING_REVIEW';
  END IF;
END $$;

-- Roles: only MIS (Admin) is kept; HOD and ONBOARD_TEAM are removed

-- Onboarding organizations (segregated from organizations)
CREATE TABLE IF NOT EXISTS onboarding_organizations (
    id           BIGSERIAL PRIMARY KEY,
    code         VARCHAR(50)  NOT NULL UNIQUE,
    name         VARCHAR(150) NOT NULL,
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    created_by   BIGINT,
    updated_by   BIGINT,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS onboarding_organization_mappings (
    id                          BIGSERIAL PRIMARY KEY,
    onboarding_organization_id  BIGINT NOT NULL REFERENCES onboarding_organizations(id),
    organization_id             BIGINT NOT NULL REFERENCES organizations(id),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (onboarding_organization_id, organization_id)
);

CREATE INDEX IF NOT EXISTS ix_onboard_org_map_onboard
  ON onboarding_organization_mappings(onboarding_organization_id);
CREATE INDEX IF NOT EXISTS ix_onboard_org_map_org
  ON onboarding_organization_mappings(organization_id);

-- Seed onboarding organizations
INSERT INTO onboarding_organizations (code, name)
SELECT v.code, v.name
FROM (VALUES
  ('BRAVENS_ONBOARD', 'Bravens Inc (Onboarding)'),
  ('AMPCUS_ONBOARD', 'Ampcus Inc (Onboarding)')
) AS v(code, name)
WHERE NOT EXISTS (
  SELECT 1 FROM onboarding_organizations o WHERE o.code = v.code AND o.deleted_at IS NULL
);

-- Map Bravens onboarding → Bravens Inc, Apokrin LLC, Bravens Tech variants
INSERT INTO onboarding_organization_mappings (onboarding_organization_id, organization_id)
SELECT oo.id, org.id
FROM onboarding_organizations oo
CROSS JOIN organizations org
WHERE oo.code = 'BRAVENS_ONBOARD'
  AND oo.deleted_at IS NULL
  AND org.deleted_at IS NULL
  AND lower(org.name) IN (
    lower('Bravens Inc'),
    lower('Apokrin LLC'),
    lower('Bravens Tech'),
    lower('BravensTech'),
    lower('Bravens Technologies')
  )
  AND NOT EXISTS (
    SELECT 1 FROM onboarding_organization_mappings m
    WHERE m.onboarding_organization_id = oo.id AND m.organization_id = org.id
  );

-- Map Ampcus onboarding → Ampcus Inc, ITech Inc
INSERT INTO onboarding_organization_mappings (onboarding_organization_id, organization_id)
SELECT oo.id, org.id
FROM onboarding_organizations oo
CROSS JOIN organizations org
WHERE oo.code = 'AMPCUS_ONBOARD'
  AND oo.deleted_at IS NULL
  AND org.deleted_at IS NULL
  AND lower(org.name) IN (lower('Ampcus Inc'), lower('ITech Inc'))
  AND NOT EXISTS (
    SELECT 1 FROM onboarding_organization_mappings m
    WHERE m.onboarding_organization_id = oo.id AND m.organization_id = org.id
  );

-- User onboarding organization assignment (only for ONBOARD_TEAM)
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS onboarding_organization_id BIGINT
    REFERENCES onboarding_organizations(id);

CREATE INDEX IF NOT EXISTS ix_users_onboarding_org
  ON users(onboarding_organization_id)
  WHERE deleted_at IS NULL AND onboarding_organization_id IS NOT NULL;

-- Head of Department on candidate starts
ALTER TABLE candidate_start
  ADD COLUMN IF NOT EXISTS head_of_department VARCHAR(150);
