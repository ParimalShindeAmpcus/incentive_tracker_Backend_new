from fastapi import APIRouter

from mis.api.v1.endpoints import (
    aliases,
    auth,
    profile,
    dashboard,
    users,
    teams,
    starts,
    incentives,
    performance,
    reports,
    master_data,
    email_templates,
    settings,
    jobdiva,
    exports,
    notifications,
    audit_logs,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(profile.router, prefix="/profile", tags=["profile"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(aliases.router, tags=["aliases"])
api_router.include_router(teams.router, prefix="/teams", tags=["teams"])
api_router.include_router(starts.router, prefix="/starts", tags=["starts"])
api_router.include_router(incentives.router, prefix="/incentives", tags=["incentives"])
api_router.include_router(performance.router, prefix="/performance", tags=["performance"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(master_data.router, prefix="/master-data", tags=["master-data"])
api_router.include_router(email_templates.router, prefix="/email-templates", tags=["email-templates"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(jobdiva.router, prefix="/jobdiva", tags=["jobdiva"])
api_router.include_router(exports.router, prefix="/exports", tags=["exports"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(audit_logs.router, prefix="/audit-logs", tags=["audit-logs"])
