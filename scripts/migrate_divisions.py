"""Add description, calculation_engine, updated_at to divisions table and backfill defaults."""

from sqlalchemy import text
from prism.core.db import get_engine

def run_migration():
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE divisions ADD COLUMN IF NOT EXISTS description TEXT"))
        conn.execute(text("ALTER TABLE divisions ADD COLUMN IF NOT EXISTS calculation_engine VARCHAR(50) DEFAULT 'MARGIN_SLABS_PRO_RATA'"))
        conn.execute(text("ALTER TABLE divisions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ"))
        
        conn.execute(text("""
            UPDATE divisions 
            SET calculation_engine = 'MARGIN_SLABS_PRO_RATA',
                description = 'W2 & C2C margin bands ($1 to $50) with 160h pro-rata benchmark, one-time leadership bonuses, and FTE placement volume slabs.'
            WHERE code = 'nashik'
        """))
        conn.execute(text("""
            UPDATE divisions 
            SET calculation_engine = 'MARGIN_HOURS_MATRIX',
                description = '8×5 margin tier by cumulative hours matrix (Tables 1–5), fixed W2/C2C leadership payouts on 160h cumulative, and FTE finder fee policies.'
            WHERE code = 'sambhajiNagar'
        """))
        conn.execute(text("""
            UPDATE divisions 
            SET calculation_engine = 'CLIENT_MARKUP_PERCENT',
                description = 'Client markup % slabs (<5% to >40%) with role-wise payout distributions, plus internal in-house starts rates.'
            WHERE code = 'ampcusTechClient'
        """))
        conn.execute(text("""
            UPDATE divisions 
            SET calculation_engine = 'INHOUSE_FLAT_RATES',
                description = 'Internal in-house placements fixed payout rates.'
            WHERE code = 'ampcusTechInhouse'
        """))
        print("Divisions table migrated and populated successfully!")

if __name__ == "__main__":
    run_migration()
