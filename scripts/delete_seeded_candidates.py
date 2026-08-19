"""Remove demo/seed candidate rows from the database.

Usage (from incentive_tracker_Backend_new):
    python scripts/delete_seeded_candidates.py
    python scripts/delete_seeded_candidates.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app.core.db import get_engine
from app.services.cycles.cycle_candidates import is_seed_candidate
from app.repositories.entities.candidate import Candidate
from sqlalchemy.orm import sessionmaker


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete seeded/demo candidates")
    parser.add_argument("--dry-run", action="store_true", help="List rows only; do not delete")
    args = parser.parse_args()

    SessionLocal = sessionmaker(bind=get_engine())
    db = SessionLocal()
    try:
        rows = db.query(Candidate).all()
        seed_rows = [row for row in rows if is_seed_candidate(row)]
        version_labels = (
            "converted-report-seed-all",
            "reports-bulk-seed-v1",
            "reports-demo-v1",
            "seed_10_per_division",
        )
        version_ids = [
            row[0]
            for row in db.execute(
                text(
                    """
                    SELECT id FROM candidate_data_versions
                    WHERE version_label = ANY(:labels)
                       OR source_filename ILIKE '%seed%'
                       OR notes ILIKE '%seed%'
                    """
                ),
                {"labels": list(version_labels)},
            ).fetchall()
        ]
        if version_ids:
            version_seed = (
                db.query(Candidate).filter(Candidate.source_version_id.in_(version_ids)).all()
            )
            seen = {row.id for row in seed_rows}
            seed_rows.extend(row for row in version_seed if row.id not in seen)

        if not seed_rows:
            print("No seeded candidates found.")
            return

        print(f"Found {len(seed_rows)} seeded candidate(s):")
        for row in seed_rows:
            print(f"  - id={row.id} name={row.candidate_name!r} ext={row.external_candidate_id!r}")

        if args.dry_run:
            print("Dry run — nothing deleted.")
            return

        ids = [row.id for row in seed_rows]
        db.execute(
            text("DELETE FROM cycle_payment_statuses WHERE candidate_id = ANY(:ids)"),
            {"ids": ids},
        )
        db.execute(
            text("DELETE FROM incentive_lines WHERE candidate_id = ANY(:ids)"),
            {"ids": ids},
        )
        db.query(Candidate).filter(Candidate.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        print(f"Deleted {len(ids)} seeded candidate(s).")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
