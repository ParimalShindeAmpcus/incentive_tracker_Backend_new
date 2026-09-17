"""
One-time migration: Remove ACCOUNTS and VIEWER roles from the database using raw SQL.
Safe, no ORM relationship conflicts.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.db import get_engine

ROLES_TO_REMOVE = ("ACCOUNTS", "VIEWER")

def main():
    engine = get_engine()
    with engine.begin() as conn:
        # 1. Get IDs of roles to remove
        rows = conn.execute(
            __import__("sqlalchemy").text(
                "SELECT id, name FROM roles WHERE name IN :names"
            ),
            {"names": ROLES_TO_REMOVE},
        ).fetchall()

        if not rows:
            print("No ACCOUNTS or VIEWER roles found. Nothing to do.")
            return

        role_ids = [r[0] for r in rows]
        role_names = [r[1] for r in rows]
        print(f"Found roles to remove: {role_names} (ids={role_ids})")

        # 2. Get ADMIN role id
        admin_row = conn.execute(
            __import__("sqlalchemy").text("SELECT id FROM roles WHERE name = 'ADMIN'")
        ).fetchone()
        admin_id = admin_row[0] if admin_row else None

        # 3. For each role being removed, promote users who have it but not ADMIN
        if admin_id:
            for role_id in role_ids:
                users_with_role = conn.execute(
                    __import__("sqlalchemy").text(
                        "SELECT user_id FROM user_roles WHERE role_id = :rid"
                    ),
                    {"rid": role_id},
                ).fetchall()

                for (user_id,) in users_with_role:
                    already_admin = conn.execute(
                        __import__("sqlalchemy").text(
                            "SELECT 1 FROM user_roles WHERE user_id = :uid AND role_id = :aid"
                        ),
                        {"uid": user_id, "aid": admin_id},
                    ).fetchone()

                    if not already_admin:
                        conn.execute(
                            __import__("sqlalchemy").text(
                                "INSERT INTO user_roles (user_id, role_id) VALUES (:uid, :aid)"
                            ),
                            {"uid": user_id, "aid": admin_id},
                        )
                        print(f"  Promoted user id={user_id} to ADMIN.")

        # 4. Delete user_roles entries for the old roles
        for role_id in role_ids:
            result = conn.execute(
                __import__("sqlalchemy").text(
                    "DELETE FROM user_roles WHERE role_id = :rid"
                ),
                {"rid": role_id},
            )
            print(f"  Deleted {result.rowcount} user_roles row(s) for role id={role_id}.")

        # 5. Delete the roles themselves
        result = conn.execute(
            __import__("sqlalchemy").text(
                "DELETE FROM roles WHERE name IN :names"
            ),
            {"names": ROLES_TO_REMOVE},
        )
        print(f"  Deleted {result.rowcount} role(s): {role_names}.")

    print("\nDone. Only ADMIN role remains in the database.")


if __name__ == "__main__":
    main()
