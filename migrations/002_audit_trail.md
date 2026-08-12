# Migration 002 — Audit trail frontend alignment

Aligns `audit_logs` with the frontend `AuditLogItem` contract.

## New / changed columns

| Column | Type | Notes |
|--------|------|-------|
| `title` | `VARCHAR(255) NOT NULL DEFAULT ''` | Activity title |
| `user_display` | `VARCHAR(255) NOT NULL DEFAULT ''` | Maps to frontend `user` |
| `username` | `VARCHAR(255) NOT NULL DEFAULT ''` | Actor username |
| `metadata` | `JSONB` | Optional structured metadata |
| `action` | `VARCHAR(50)` | Frontend action enum values |

## PostgreSQL one-time script

Run against an existing database that already has `audit_logs`:

```sql
-- Add new columns (safe if re-run)
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS title VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS user_display VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS username VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS metadata JSONB;

-- Convert action from old enum to varchar (if old enum exists)
ALTER TABLE audit_logs ALTER COLUMN action TYPE VARCHAR(50) USING action::text;
DROP TYPE IF EXISTS audit_action_enum;
```

For a fresh dev database, `init_db()` / `create_all` will create the table with the new schema.
