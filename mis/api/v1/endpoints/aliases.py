from fastapi import APIRouter

from mis.api.v1.endpoints import master_data, recruiters

router = APIRouter()

# Frontend-compatible aliases (MIS-web services)
router.include_router(master_data.router, prefix="/admin", tags=["admin-aliases"])
router.include_router(recruiters.router, prefix="/recruiters", tags=["recruiter-aliases"])
