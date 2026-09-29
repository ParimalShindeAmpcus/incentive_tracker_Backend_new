"""
Migration script to merge 'mis_db' (Starts MIS) and 'incentive_tracker' (PRISM)
into a single standalone PostgreSQL database 'mis_prism_db' with schema separation.

Schemas created in 'mis_prism_db':
  - 'mis': contains all tables, sequences, enums, triggers, and data from mis_db
  - 'prism': contains all tables, sequences, views, types, and data from incentive_tracker
  - 'public': extensions (citext) and shared utilities

Source databases ('mis_db' and 'incentive_tracker') are left completely untouched.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Find PostgreSQL tools
def find_pg_tool(name: str) -> str:
    # 1. PATH
    which_path = shutil.which(name)
    if which_path:
        return which_path
    # 2. Windows standard installation locations
    for version in ["18", "17", "16", "15", "14", "13"]:
        candidate = Path(rf"C:\Program Files\PostgreSQL\{version}\bin\{name}.exe")
        if candidate.exists():
            return str(candidate)
    raise RuntimeError(f"Could not locate {name} or {name}.exe. Please ensure PostgreSQL client tools are installed.")


def merge_databases(
    host: str = "localhost",
    port: int = 5432,
    user: str = "postgres",
    password: str = "admin@123",
    source_mis_db: str = "mis_db",
    source_prism_db: str = "incentive_tracker",
    target_db: str = "mis_prism_db",
):
    pg_dump = find_pg_tool("pg_dump")
    psql = find_pg_tool("psql")

    print(f"Connecting to PostgreSQL at {host}:{port} as user '{user}'...")
    conn = psycopg2.connect(host=host, port=port, user=user, password=password, dbname="postgres")
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    # Terminate any active sessions on source and target databases
    cur.execute(f"""
        SELECT pg_terminate_backend(pid) 
        FROM pg_stat_activity 
        WHERE datname IN ('{source_mis_db}', '{source_prism_db}', '{target_db}', 'temp_prism_migrate') 
          AND pid <> pg_backend_pid();
    """)

    # Check that source databases exist
    cur.execute("SELECT datname FROM pg_database WHERE datname IN (%s, %s);", (source_mis_db, source_prism_db))
    found = {r[0] for r in cur.fetchall()}
    if source_mis_db not in found:
        raise RuntimeError(f"Source database '{source_mis_db}' does not exist.")
    if source_prism_db not in found:
        raise RuntimeError(f"Source database '{source_prism_db}' does not exist.")

    print(f"[1/6] Recreating target database '{target_db}' from template '{source_mis_db}'...")
    cur.execute(f"DROP DATABASE IF EXISTS {target_db};")
    cur.execute(f"CREATE DATABASE {target_db} TEMPLATE {source_mis_db};")

    print(f"[2/6] In '{target_db}', renaming schema 'public' to 'mis' and initializing clean 'public'...")
    conn_target = psycopg2.connect(host=host, port=port, user=user, password=password, dbname=target_db)
    conn_target.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur_target = conn_target.cursor()
    cur_target.execute("ALTER SCHEMA public RENAME TO mis;")
    cur_target.execute("CREATE SCHEMA public;")
    cur_target.execute("CREATE EXTENSION IF NOT EXISTS citext SCHEMA public;")
    cur_target.execute(f"GRANT ALL ON SCHEMA public TO {user};")
    cur_target.execute(f"GRANT ALL ON SCHEMA mis TO {user};")
    conn_target.close()

    print(f"[3/6] Creating temporary clone 'temp_prism_migrate' from template '{source_prism_db}'...")
    cur.execute("DROP DATABASE IF EXISTS temp_prism_migrate;")
    cur.execute(f"CREATE DATABASE temp_prism_migrate TEMPLATE {source_prism_db};")

    print("[4/6] Renaming schema 'public' to 'prism' in temporary clone...")
    conn_temp = psycopg2.connect(host=host, port=port, user=user, password=password, dbname="temp_prism_migrate")
    conn_temp.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur_temp = conn_temp.cursor()
    cur_temp.execute("ALTER SCHEMA public RENAME TO prism;")
    conn_temp.close()

    print(f"[5/6] Exporting 'prism' schema and importing into '{target_db}'...")
    with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as tf:
        temp_sql = tf.name

    env = os.environ.copy()
    env["PGPASSWORD"] = password

    try:
        dump_cmd = [
            pg_dump,
            "-h", host,
            "-p", str(port),
            "-U", user,
            "-n", "prism",
            "-f", temp_sql,
            "temp_prism_migrate"
        ]
        subprocess.run(dump_cmd, check=True, env=env)

        restore_cmd = [
            psql,
            "-h", host,
            "-p", str(port),
            "-U", user,
            "-d", target_db,
            "-f", temp_sql
        ]
        subprocess.run(restore_cmd, check=True, env=env, stdout=subprocess.DEVNULL)
    finally:
        if os.path.exists(temp_sql):
            try:
                os.remove(temp_sql)
            except Exception:
                pass

    print("[6/6] Cleaning up temporary clone...")
    cur.execute("""
        SELECT pg_terminate_backend(pid) 
        FROM pg_stat_activity 
        WHERE datname = 'temp_prism_migrate' AND pid <> pg_backend_pid();
    """)
    cur.execute("DROP DATABASE temp_prism_migrate;")
    conn.close()

    # Verification
    print("\nVerifying merged database:")
    conn_verify = psycopg2.connect(host=host, port=port, user=user, password=password, dbname=target_db)
    cur_verify = conn_verify.cursor()
    for schema_name in ["mis", "prism"]:
        cur_verify.execute(f"""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema='{schema_name}' AND table_type='BASE TABLE' 
            ORDER BY table_name;
        """)
        tables = [r[0] for r in cur_verify.fetchall()]
        print(f"  Schema '{schema_name}': {len(tables)} tables preserved.")
    conn_verify.close()
    print(f"\nSUCCESS: Unified database '{target_db}' is ready for both MIS and PRISM applications!")


if __name__ == "__main__":
    from mis.core.config import settings as mis_s
    from prism.config import get_settings as get_prism_s

    p_settings = get_prism_s()
    merge_databases(
        host=mis_s.DB_HOST,
        port=mis_s.PORT,
        user=mis_s.DB_USER,
        password=mis_s.PASSWORD,
        source_mis_db="mis_db",
        source_prism_db="incentive_tracker",
        target_db="mis_prism_db",
    )
