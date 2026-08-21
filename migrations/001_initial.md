# Initial schema (scaffold)

Tables are created via SQLAlchemy `Base.metadata.create_all` in `app.core.db.init_db()`.

There is no Alembic migration yet. Run either:

- `python scripts/create_db.py` (ensures DB exists, then `init_db()` + seed)
- App startup lifespan (when `seed_on_startup=True`)

## Entities registered (28 logical tables)

From `app/repositories/entities/`:

- **Auth / users:** `roles`, `users`, `user_roles`
- **Organization:** `organizations`, `divisions`, `employees`
- **Candidates:** `candidate_data_versions`, `candidates`
- **Recruiters:** `recruiter_master_versions`, `recruiter_statuses`
- **Hours:** `hours_data_versions`, `hours_rows`, `hours_benchmarks`
- **Project end:** `project_end_versions`, `project_end_records`
- **Cycles:** `incentive_cycles`, `cycle_data_snapshots`, `cycle_hours_matches`, `cycle_validation_results`, `cycle_checklist_items`, `cycle_payment_statuses`, `cycle_manual_adjustments`, `cycle_approval_results`
- **Incentives:** `incentive_lines`, `incentive_approvals`, `incentive_payments`, `paid_incentive_ledger`, `incentive_slabs`
- **Audit:** `audit_logs`

Enums are created by SQLAlchemy where the dialect supports them (`cycle_status_enum`, `match_result_enum`, `recruiter_status_enum`, `audit_action_enum`).

Seed (idempotent) adds ADMIN/ACCOUNTS/VIEWER roles, default admin user, DEFAULT organization with four divisions, hours benchmarks (160), and sample Nashik slabs.
