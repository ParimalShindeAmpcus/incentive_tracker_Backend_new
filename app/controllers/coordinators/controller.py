from typing import Optional
from fastapi import APIRouter, File, Query, UploadFile, status
from app.models.coordinators.schemas import BulkMarkLeftResponse, BulkUploadResponse, CoordinatorInput, CoordinatorOut, CoordinatorPage, CoordinatorStatusUpdate, CoordinatorSummary, CoordinatorUpdate
from app.repositories.entities.coordinator import CoordinatorStatus
from app.services.common.deps import CurrentUser, DbSession
from app.services.coordinators import coordinator_service
router = APIRouter()
@router.get("", response_model=CoordinatorPage)
def list_coordinators(db: DbSession, page:int=Query(1,ge=1), page_size:int=Query(50,ge=1,le=500), search:Optional[str]=None, employment_status:Optional[CoordinatorStatus]=None): return coordinator_service.list_coordinators(db,page,page_size,search,employment_status)
@router.get("/summary", response_model=CoordinatorSummary)
def get_summary(db: DbSession): return coordinator_service.summary(db)
@router.post("", response_model=CoordinatorOut, status_code=status.HTTP_201_CREATED)
def create_coordinator(payload: CoordinatorInput, db: DbSession, user: CurrentUser): return coordinator_service.create(db,payload)
@router.post("/bulk-upload", response_model=BulkUploadResponse)
async def bulk_upload(db: DbSession, user: CurrentUser, file: UploadFile = File(...)): return coordinator_service.bulk_upload(db, await file.read(), file.filename or "coordinators.csv")
@router.post("/bulk-mark-left", response_model=BulkMarkLeftResponse)
async def bulk_mark_left(db: DbSession, user: CurrentUser, file: UploadFile = File(...)): return coordinator_service.bulk_mark_left(db, await file.read(), file.filename or "left-coordinators.csv")
@router.get("/{coordinator_id}", response_model=CoordinatorOut)
def get_coordinator(coordinator_id:int, db:DbSession): return coordinator_service.get_coordinator(db,coordinator_id)
@router.patch("/{coordinator_id}", response_model=CoordinatorOut)
def update_coordinator(coordinator_id:int,payload:CoordinatorUpdate,db:DbSession,user:CurrentUser): return coordinator_service.update(db,coordinator_id,payload)
@router.post("/{coordinator_id}/employment-status", response_model=CoordinatorOut)
def update_status(coordinator_id:int,payload:CoordinatorStatusUpdate,db:DbSession,user:CurrentUser): return coordinator_service.update_status(db,coordinator_id,payload)
@router.delete("/{coordinator_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_coordinator(coordinator_id:int,db:DbSession,user:CurrentUser): coordinator_service.delete_left(db,coordinator_id)
