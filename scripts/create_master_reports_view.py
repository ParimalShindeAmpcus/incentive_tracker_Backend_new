from __future__ import annotations

import sys
from pathlib import Path
import os
import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def main() -> None:
    load_dotenv()
    conn = psycopg2.connect(
        dbname=os.environ.get("DB_NAME", "incentive_tracker"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", "admin@123"),
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432")
    )
    conn.autocommit = True
    cur = conn.cursor()

    try:
        print("Creating master_reports_view...")
        cur.execute("""
            CREATE OR REPLACE VIEW master_reports_view AS
            SELECT
                il.id AS line_id,
                il.person AS person,
                il.role AS role,
                il.candidate_name AS line_candidate_name,
                il.amount AS amount,
                il.hours AS hours,
                il.margin AS line_margin,
                il.incentive_type AS incentive_type,
                il.eligible AS eligible,
                
                ic.id AS cycle_id,
                ic.name AS cycle_name,
                ic.division AS division,
                ic.incentive_month AS incentive_month,
                ic.status AS cycle_status,
                
                c.external_candidate_id AS external_candidate_id,
                c.candidate_name AS candidate_name,
                c.start_date AS start_date,
                c.contract_type AS contract_type,
                c.candidate_source AS candidate_source,
                c.organization AS organization,
                c.margin AS candidate_margin,
                c.crm AS crm,
                c.center_head AS center_head,
                c.associate_director AS associate_director,
                c.manager AS manager,
                c.senior_manager AS senior_manager,
                c.team_lead AS team_lead
            FROM incentive_lines il
            JOIN incentive_cycles ic ON ic.id = il.cycle_id
            LEFT JOIN candidates c ON c.id = il.candidate_id;
        """)
        print("Success! View created.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
