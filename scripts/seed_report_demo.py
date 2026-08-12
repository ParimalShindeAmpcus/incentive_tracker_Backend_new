"""
Seed a small APPROVED cycle + candidates + incentive_lines for Reports testing.

Uses raw SQL against columns present on current Postgres schema.

Usage (from incentive-api/):

    python scripts/seed_report_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    from app.core.db import get_engine, init_db
    from app.services.common.seed import seed_database

    init_db()
    seed_database()

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    db = SessionLocal()
    try:
        existing = db.execute(
            text("SELECT id FROM incentive_cycles WHERE name = :n LIMIT 1"),
            {"n": "Reports Demo Cycle"},
        ).scalar()
        if existing:
            line_count = db.execute(
                text("SELECT COUNT(*) FROM incentive_lines WHERE cycle_id = :cid"),
                {"cid": existing},
            ).scalar()
            print(f"Demo cycle already exists id={existing} lines={line_count}")
            return

        version_id = db.execute(
            text(
                """
                INSERT INTO candidate_data_versions
                    (version_label, source_filename, division, row_count, notes)
                VALUES
                    ('reports-demo-v1', 'seed_report_demo.py', 'nashik', 2, 'Reports E2E seed')
                RETURNING id
                """
            )
        ).scalar()

        c1 = db.execute(
            text(
                """
                INSERT INTO candidates (
                    external_candidate_id, candidate_name, normalized_name,
                    contract_type, margin, start_date, recruiter, team_lead, crm,
                    candidate_source, organization, division,
                    source_version_id, last_touched_version_id, is_active, incentive_active
                ) VALUES (
                    'AMSUB24-2495', 'Aisha Mayes', 'aisha mayes',
                    'C2C', 12, '2023-10-10', 'Amit William Ohol', 'Nitin Giri', 'Majid Khan',
                    'Ampcus Inc', 'Ampcus Inc', 'nashik',
                    :vid, :vid, true, true
                ) RETURNING id
                """
            ),
            {"vid": version_id},
        ).scalar()

        c2 = db.execute(
            text(
                """
                INSERT INTO candidates (
                    external_candidate_id, candidate_name, normalized_name,
                    contract_type, margin, start_date, recruiter, team_lead, crm,
                    candidate_source, organization, division,
                    source_version_id, last_touched_version_id, is_active, incentive_active
                ) VALUES (
                    'BraW22026-1984', 'Jackeline Reveles', 'jackeline reveles',
                    'C2C', 4.23, '2026-01-27', 'Demo Recruiter', 'Avinash Kumar', 'Avinash Kumar',
                    'Bravens Inc', 'Bravens Inc', 'nashik',
                    :vid, :vid, true, true
                ) RETURNING id
                """
            ),
            {"vid": version_id},
        ).scalar()

        cycle_id = db.execute(
            text(
                """
                INSERT INTO incentive_cycles (
                    name, division, incentive_month, cycle_start_date, cycle_end_date,
                    remarks, status, candidate_version_id, approved_at
                ) VALUES (
                    'Reports Demo Cycle', 'nashik', '2026-02', '2026-02-01', '2026-02-28',
                    'Seeded for reports E2E', 'APPROVED', :vid, NOW()
                ) RETURNING id
                """
            ),
            {"vid": version_id},
        ).scalar()

        lines = [
            (c1, "Aisha Mayes", "Recruiter", "Amit William Ohol", "RECURRING", 2500, 160, 12),
            (c1, "Aisha Mayes", "Team Lead", "Nitin Giri", "RECURRING", 250, 160, 12),
            (c2, "Jackeline Reveles", "AVP", "Avinash Kumar Vijay Kumar Prasad", "ONE_TIME", 2300, 88.15, 4.23),
        ]
        for cand_id, cname, role, person, itype, amount, hours, margin in lines:
            db.execute(
                text(
                    """
                    INSERT INTO incentive_lines (
                        cycle_id, candidate_id, candidate_name, role, person,
                        incentive_type, rule_applied, eligible, base_incentive,
                        pro_rata_factor, amount, hours, margin, reason, payment_status
                    ) VALUES (
                        :cycle_id, :candidate_id, :candidate_name, :role, :person,
                        :incentive_type, 'demo', true, :amount,
                        1, :amount, :hours, :margin, 'Reports demo', 'UNPAID'
                    )
                    """
                ),
                {
                    "cycle_id": cycle_id,
                    "candidate_id": cand_id,
                    "candidate_name": cname,
                    "role": role,
                    "person": person,
                    "incentive_type": itype,
                    "amount": amount,
                    "hours": hours,
                    "margin": margin,
                },
            )

        db.commit()
        print(f"Created demo cycle id={cycle_id} with {len(lines)} incentive lines")
        print("Call GET /api/v1/reports after login")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
