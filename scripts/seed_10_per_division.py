from __future__ import annotations

import sys
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def main() -> None:
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
    from app.core.db import get_engine, init_db

    init_db()

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    db = SessionLocal()
    try:
        # Create a single version ID
        version_id = db.execute(
            text(
                """
                INSERT INTO candidate_data_versions
                    (version_label, source_filename, division, row_count, notes)
                VALUES
                    ('reports-bulk-seed-v1', 'seed_10_per_division.py', 'all', 40, 'Reports Bulk Seed')
                RETURNING id
                """
            )
        ).scalar()

        divisions = [
            ("nashik", "Nashik Recruiter"),
            ("sambhajiNagar", "Sambhaji Recruiter"),
            ("ampcusTechClient", "Client Recruiter"),
            ("ampcusTechInhouse", "Inhouse Recruiter"),
        ]

        for idx, (div_key, recruiter_name) in enumerate(divisions):
            print(f"Seeding for division: {div_key}")
            # Create a cycle for this division
            cycle_id = db.execute(
                text(
                    """
                    INSERT INTO incentive_cycles (
                        name, division, incentive_month, cycle_start_date, cycle_end_date,
                        remarks, status, candidate_version_id, approved_at
                    ) VALUES (
                        :name, :division, '2026-03', '2026-03-01', '2026-03-31',
                        'Bulk seeded cycle', 'APPROVED', :vid, NOW()
                    ) RETURNING id
                    """
                ),
                {
                    "name": f"{div_key} Bulk Cycle",
                    "division": div_key,
                    "vid": version_id
                }
            ).scalar()

            for i in range(1, 11):
                cand_name = f"Sample Cand {i} {div_key}"
                cand_id = db.execute(
                    text(
                        """
                        INSERT INTO candidates (
                            external_candidate_id, candidate_name, normalized_name,
                            contract_type, margin, start_date, recruiter, team_lead, crm,
                            candidate_source, organization, division,
                            source_version_id, last_touched_version_id, is_active, incentive_active
                        ) VALUES (
                            :ext_id, :cname, :nname,
                            'C2C', 10, '2026-01-01', :rec, 'Sample Team Lead', 'Sample CRM',
                            'Sample Source', 'Sample Org', :div,
                            :vid, :vid, true, true
                        ) RETURNING id
                        """
                    ),
                    {
                        "ext_id": f"BULK-{div_key}-{i}",
                        "cname": cand_name,
                        "nname": cand_name.lower(),
                        "rec": recruiter_name,
                        "div": div_key,
                        "vid": version_id
                    }
                ).scalar()

                db.execute(
                    text(
                        """
                        INSERT INTO incentive_lines (
                            cycle_id, candidate_id, candidate_name, role, person,
                            incentive_type, rule_applied, eligible, base_incentive,
                            pro_rata_factor, amount, hours, margin, reason, payment_status
                        ) VALUES (
                            :cycle_id, :candidate_id, :candidate_name, 'Recruiter', :person,
                            'RECURRING', 'bulk_demo', true, 1000,
                            1, 1000, 160, 10, 'Bulk seed demo', 'UNPAID'
                        )
                        """
                    ),
                    {
                        "cycle_id": cycle_id,
                        "candidate_id": cand_id,
                        "candidate_name": cand_name,
                        "person": recruiter_name,
                    }
                )

        db.commit()
        print("Successfully seeded 10 records per division.")
    except Exception as e:
        db.rollback()
        print(f"Error seeding: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
