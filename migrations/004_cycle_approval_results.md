# Cycle approval results

Start-cycle records are stored in **`incentive_cycles`**. That table is created when a cycle is started (`POST /cycles`) and holds the cycle header (name, division, incentive month, dates, status, source-version FKs).

Working calculation rows stay in **`incentive_lines`** until approval.

On **Approve**, the frozen payout snapshot is written to:

## `cycle_approval_results`

One row per incentive line at the moment the approval workflow completes. Re-approving a cycle replaces that cycle's snapshot (idempotent). Existing `APPROVED` / `PAID` / `CLOSED` cycles are backfilled on app startup if they have no snapshot yet.

Created via SQLAlchemy `Base.metadata.create_all` (same as the rest of the schema). Foreign keys:

- `cycle_id` → `incentive_cycles.id` (CASCADE)
- `incentive_line_id` → `incentive_lines.id` (SET NULL)
- `candidate_id` → `candidates.id` (SET NULL)
- `approved_by` → `users.id`

Reports (`approved_only=true`) and approved Excel export read from this table so later edits to Candidate Master or recalculation of `incentive_lines` cannot change a completed cycle's results.
