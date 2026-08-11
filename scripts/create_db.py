"""
Create PostgreSQL database if missing, then init tables + seed.

Usage (from repo root):

    python scripts/create_db.py
    python scripts/create_db.py --reset   # DROP + recreate public schema (destructive)

Requires .env with DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME
(or DATABASE_URL).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_settings():
    from app.config import get_settings

    get_settings.cache_clear()
    return get_settings()


def ensure_database(settings) -> str:
    """Create the target database on Postgres when missing."""
    url = make_url(settings.database_url)
    if url.get_backend_name() == "sqlite":
        print(f"Using SQLite at {url.database}")
        return settings.database_url

    db_name = url.database
    if not db_name:
        raise SystemExit("DATABASE_URL / DB_NAME is required")

    admin_url = url.set(database="postgres")
    engine = create_engine(admin_url.render_as_string(hide_password=False), isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": db_name},
        ).scalar()
        if not exists:
            print(f"Creating database '{db_name}'...")
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
            print("Database created.")
        else:
            print(f"Database '{db_name}' already exists.")
    engine.dispose()
    return settings.database_url


def reset_schema(database_url: str) -> None:
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite":
        db_path = Path(url.database or "")
        if db_path.exists():
            db_path.unlink()
            print(f"Deleted SQLite file {db_path}")
        return

    engine = create_engine(database_url)
    with engine.begin() as conn:
        print("Dropping and recreating public schema...")
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
    engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create DB for Incentive Tracker (scaffold)")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop public schema (Postgres) or SQLite file",
    )
    args = parser.parse_args()

    settings = _load_settings()
    print(f"Target backend: {make_url(settings.database_url).get_backend_name()}")
    print(f"DB name: {make_url(settings.database_url).database}")

    database_url = ensure_database(settings)
    if args.reset:
        reset_schema(database_url)

    from app.core.db import init_db
    from app.services.common.seed import seed_database

    print("Creating tables via SQLAlchemy metadata.create_all / init_db()...")
    init_db()
    print("Seeding default roles, admin, org/divisions, benchmarks, slabs...")
    seed_database()
    print("Schema + seed complete.")

    print("\nDone.")
    print("Start API with:")
    print("  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")
    print("Health: http://127.0.0.1:8000/health")
    print("Docs: http://127.0.0.1:8000/docs")


if __name__ == "__main__":
    main()
