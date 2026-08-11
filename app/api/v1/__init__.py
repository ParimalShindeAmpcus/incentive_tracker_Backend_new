from fastapi import APIRouter

from app.api.v1 import (
    audit,
    auth,
    candidate_data,
    cycle_uploads,
    cycle_workflow,
    cycles,
    hours_data,
    project_end,
    recruiter_master,
    reports,
    vlookup,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(candidate_data.router)
api_router.include_router(recruiter_master.router)
api_router.include_router(hours_data.router)
api_router.include_router(project_end.router)
api_router.include_router(vlookup.router)
api_router.include_router(cycles.router)
api_router.include_router(cycle_workflow.router)
api_router.include_router(cycle_uploads.router)
api_router.include_router(audit.router)
api_router.include_router(reports.router)
