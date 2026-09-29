"""
Programmatic schema initialization for the FastAPI app.

Prefer the CLI for local setup:
    python scripts/create_schema.py --create-db
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND_ROOT / "scripts" / "create_schema.py"


def init_db(*, create_db: bool = True, check_only: bool = False) -> int:
    """Run the schema creation script as a subprocess. Returns exit code."""
    cmd = [sys.executable, str(SCRIPT)]
    if check_only:
        cmd.append("--check")
    elif create_db:
        cmd.append("--create-db")
    return subprocess.call(cmd, cwd=str(BACKEND_ROOT))


if __name__ == "__main__":
    raise SystemExit(init_db())
