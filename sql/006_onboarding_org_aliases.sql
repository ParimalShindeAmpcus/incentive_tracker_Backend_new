-- Ensure form organization names used in New Start are covered by onboarding mappings.
-- Bravens Inc (Onboarding) → Bravens Inc, Apokrin LLC, Bravens Tech, BravensTech, Bravens Technologies
-- Ampcus Inc (Onboarding) → Ampcus Inc, ITech Inc

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
