"""Redirect stub — migrations live under alembic/.

This file remains so older references to migrations/ do not silently break.
Use: alembic upgrade head
"""

raise SystemExit(
    "Use the alembic/ directory (alembic.ini script_location=alembic). "
    "Do not run migrations from migrations/env.py."
)
