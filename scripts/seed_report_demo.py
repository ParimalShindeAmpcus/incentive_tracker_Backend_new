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
        # Check if already seeded
        existing_nashik = db.execute(
            text("SELECT id FROM incentive_cycles WHERE name = 'August 2026 Nashik Division Cycle' LIMIT 1")
        ).scalar()
        if existing_nashik:
            print(f"Nashik demo cycle already exists id={existing_nashik}")
        else:
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
                        source_version_id, last_touched_version_id, is_active, incentive_active,
                        ownership_confirmed
                    ) VALUES (
                        'AMSUB24-2495', 'Aisha Mayes', 'aisha mayes',
                        'C2C', 12, '2023-10-10', 'Amit William Ohol', 'Nitin Giri', 'Majid Khan',
                        'Ampcus Inc', 'Ampcus Inc', 'nashik',
                        :vid, :vid, true, true, true
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
                        source_version_id, last_touched_version_id, is_active, incentive_active,
                        ownership_confirmed
                    ) VALUES (
                        'BraW22026-1984', 'Jackeline Reveles', 'jackeline reveles',
                        'W2', 8.50, '2026-01-27', 'Demo Recruiter', 'Avinash Kumar', 'Avinash Kumar',
                        'Bravens Inc', 'Bravens Inc', 'nashik',
                        :vid, :vid, true, true, true
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
                        'August 2026 Nashik Division Cycle', 'nashik', '2026-08', '2026-08-01', '2026-08-31',
                        'Seeded for reports E2E', 'APPROVED', :vid, NOW()
                    ) RETURNING id
                    """
                ),
                {"vid": version_id},
            ).scalar()

            lines = [
                (c1, "Aisha Mayes", "Recruiter", "Amit William Ohol", "RECURRING", 3500, 160, 12, "Nashik margin per hour slab"),
                (c1, "Aisha Mayes", "Team Lead", "Nitin Giri", "RECURRING", 250, 160, 12, "Nashik team lead recurring"),
                (c2, "Jackeline Reveles", "Recruiter", "Demo Recruiter", "RECURRING", 2000, 160, 8.50, "Nashik margin per hour slab"),
                (c2, "Jackeline Reveles", "CRM", "Avinash Kumar", "ONE_TIME", 1000, 160, 8.50, "Nashik leadership one-time"),
            ]
            for cand_id, cname, role, person, itype, amount, hours, margin, rule in lines:
                line_id = db.execute(
                    text(
                        """
                        INSERT INTO incentive_lines (
                            cycle_id, candidate_id, candidate_name, role, person,
                            incentive_type, rule_applied, eligible, base_incentive,
                            pro_rata_factor, amount, hours, margin, reason, payment_status
                        ) VALUES (
                            :cycle_id, :candidate_id, :candidate_name, :role, :person,
                            :incentive_type, :rule, true, :amount,
                            1, :amount, :hours, :margin, 'Reports demo', 'UNPAID'
                        ) RETURNING id
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
                        "rule": rule,
                    },
                ).scalar()

                db.execute(
                    text(
                        """
                        INSERT INTO cycle_approval_results (
                            cycle_id, incentive_line_id, candidate_id, cycle_name,
                            division, incentive_month, cycle_start_date, cycle_end_date,
                            cycle_status, candidate_name, external_candidate_id,
                            start_date, contract_type, candidate_source, organization,
                            role, person, incentive_type, rule_applied, eligible,
                            base_incentive, pro_rata_factor, amount, hours, margin,
                            payment_status, approved_at
                        ) VALUES (
                            :cycle_id, :line_id, :cand_id, 'August 2026 Nashik Division Cycle',
                            'nashik', '2026-08', '2026-08-01', '2026-08-31',
                            'APPROVED', :cname, :ext_id,
                            '2026-01-27', 'W2', 'Ampcus Inc', 'Ampcus Inc',
                            :role, :person, :itype, :rule, true,
                            :amount, 1, :amount, :hours, :margin,
                            'UNPAID', NOW()
                        )
                        """
                    ),
                    {
                        "cycle_id": cycle_id,
                        "line_id": line_id,
                        "cand_id": cand_id,
                        "cname": cname,
                        "ext_id": "AMSUB24-2495" if cname == "Aisha Mayes" else "BraW22026-1984",
                        "role": role,
                        "person": person,
                        "itype": itype,
                        "rule": rule,
                        "amount": amount,
                        "hours": hours,
                        "margin": margin,
                    },
                )
            print(f"Created Nashik demo cycle id={cycle_id} with {len(lines)} lines")

        # In-House Demo Cycle
        existing_inhouse = db.execute(
            text("SELECT id FROM incentive_cycles WHERE name = 'August 2026 Ampcus Tech In-House Cycle' LIMIT 1")
        ).scalar()
        if existing_inhouse:
            print(f"In-house demo cycle already exists id={existing_inhouse}")
        else:
            v_inh = db.execute(
                text(
                    """
                    INSERT INTO candidate_data_versions
                        (version_label, source_filename, division, row_count, notes)
                    VALUES
                        ('inhouse-demo-v1', 'seed_report_demo.py', 'ampcusTechInhouse', 1, 'In-house seed')
                    RETURNING id
                    """
                )
            ).scalar()

            c_inh = db.execute(
                text(
                    """
                    INSERT INTO candidates (
                        external_candidate_id, candidate_name, normalized_name,
                        contract_type, margin, start_date, recruiter, team_lead, crm,
                        candidate_source, organization, division,
                        source_version_id, last_touched_version_id, is_active, incentive_active,
                        ownership_confirmed
                    ) VALUES (
                        'INH-2026-001', 'Sunil Deshmukh', 'sunil deshmukh',
                        'Inhouse', 0, '2026-05-01', 'Bhushan', 'Nitin Giri', 'Majid Khan',
                        'Ampcus Tech Inhouse', 'Ampcus Tech Inhouse', 'ampcusTechInhouse',
                        :vid, :vid, true, true, true
                    ) RETURNING id
                    """
                ),
                {"vid": v_inh},
            ).scalar()

            inh_cycle_id = db.execute(
                text(
                    """
                    INSERT INTO incentive_cycles (
                        name, division, incentive_month, cycle_start_date, cycle_end_date,
                        remarks, status, candidate_version_id, approved_at
                    ) VALUES (
                        'August 2026 Ampcus Tech In-House Cycle', 'ampcusTechInhouse', '2026-08', '2026-08-01', '2026-08-31',
                        'Seeded for inhouse reports E2E', 'APPROVED', :vid, NOW()
                    ) RETURNING id
                    """
                ),
                {"vid": v_inh},
            ).scalar()

            inh_line_id = db.execute(
                text(
                    """
                    INSERT INTO incentive_lines (
                        cycle_id, candidate_id, candidate_name, role, person,
                        incentive_type, rule_applied, eligible, base_incentive,
                        pro_rata_factor, amount, hours, margin, reason, payment_status
                    ) VALUES (
                        :cycle_id, :candidate_id, 'Sunil Deshmukh', 'Recruiter', 'Bhushan',
                        'INHOUSE', 'Ampcus Tech In-House 90-day rule', true, 3000,
                        1, 3000, 92, 0, '90 days completed', 'UNPAID'
                    ) RETURNING id
                    """
                ),
                {
                    "cycle_id": inh_cycle_id,
                    "candidate_id": c_inh,
                },
            ).scalar()

            db.execute(
                text(
                    """
                    INSERT INTO cycle_approval_results (
                        cycle_id, incentive_line_id, candidate_id, cycle_name,
                        division, incentive_month, cycle_start_date, cycle_end_date,
                        cycle_status, candidate_name, external_candidate_id,
                        start_date, contract_type, candidate_source, organization,
                        role, person, incentive_type, rule_applied, eligible,
                        base_incentive, pro_rata_factor, amount, hours, margin,
                        payment_status, approved_at
                    ) VALUES (
                        :cycle_id, :line_id, :cand_id, 'August 2026 Ampcus Tech In-House Cycle',
                        'ampcusTechInhouse', '2026-08', '2026-08-01', '2026-08-31',
                        'APPROVED', 'Sunil Deshmukh', 'INH-2026-001',
                        '2026-05-01', 'Inhouse', 'Ampcus Tech Inhouse', 'Ampcus Tech Inhouse',
                        'Recruiter', 'Bhushan', 'INHOUSE', 'Ampcus Tech In-House 90-day rule', true,
                        3000, 1, 3000, 92, 0,
                        'UNPAID', NOW()
                    )
                    """
                ),
                {
                    "cycle_id": inh_cycle_id,
                    "line_id": inh_line_id,
                    "cand_id": c_inh,
                },
            )
            print(f"Created In-house demo cycle id={inh_cycle_id}")

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
