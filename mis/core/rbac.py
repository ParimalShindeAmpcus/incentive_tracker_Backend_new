"""Role-based access constants — schema codes used by require_roles()."""

from mis.core.constants import ROLE_CODES

# All authenticated app users
AUTHENTICATED = ROLE_CODES

# Admin workspace (frontend "admin")
ADMIN = ("MIS",)

# Can create / submit new starts
START_CREATE = ("RECRUITER", "MIS")

# Can view starts lists (own / team / all — scoping is service-layer)
START_READ = ("RECRUITER", "MANAGER", "MIS")

# Reports & master data & user management
ADMIN_ONLY = ("MIS",)

# Manager + admin review surfaces
MANAGER_OR_ADMIN = ("MANAGER", "MIS")
