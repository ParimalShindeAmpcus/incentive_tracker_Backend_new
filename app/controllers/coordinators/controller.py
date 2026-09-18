from typing import Annotated, Optional
from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from app.models.coordinators.schemas import BulkUploadResponse, CoordinatorInput, CoordinatorOut, CoordinatorPage, CoordinatorStatusUpdate, CoordinatorSummary, CoordinatorUpdate
from app.repositories.entities.coordinator import CoordinatorStatus
from app.repositories.entities.user import User
from app.services.common.deps import CurrentUser, DbSession, get_current_user, require_roles
from app.services.coordinators import coordinator_service

router = APIRouter(dependencies=[Depends(get_current_user)])

@router.get("", response_model=CoordinatorPage)
def list_coordinators(db: DbSession, page:int=Query(1,ge=1), page_size:int=Query(50,ge=1,le=500), search:Optional[str]=None, employment_status:Optional[CoordinatorStatus]=None): return coordinator_service.list_coordinators(db,page,page_size,search,employment_status)
@router.get("/summary", response_model=CoordinatorSummary)
def get_summary(db: DbSession): return coordinator_service.summary(db)
@router.post("", response_model=CoordinatorOut, status_code=status.HTTP_201_CREATED)
def create_coordinator(payload: CoordinatorInput, db: DbSession, user: Annotated[User, Depends(require_roles("ADMIN"))]): return coordinator_service.create(db, payload, user=user)
@router.post("/bulk-upload", response_model=BulkUploadResponse)
async def bulk_upload(db: DbSession, user: Annotated[User, Depends(require_roles("ADMIN"))], file: UploadFile = File(...)):
    from app.security.upload import validate_coordinator_upload

    content = validate_coordinator_upload(file)
    return coordinator_service.bulk_upload(db, content, file.filename or "coordinators.xlsx", user=user)
@router.get("/{coordinator_id}", response_model=CoordinatorOut)
def get_coordinator(coordinator_id:int, db:DbSession): return coordinator_service.get_coordinator(db,coordinator_id)
@router.patch("/{coordinator_id}", response_model=CoordinatorOut)
def update_coordinator(coordinator_id:int,payload:CoordinatorUpdate,db:DbSession,user: Annotated[User, Depends(require_roles("ADMIN"))]): return coordinator_service.update(db,coordinator_id,payload,user=user)
@router.post("/{coordinator_id}/employment-status", response_model=CoordinatorOut)
def update_status(coordinator_id:int,payload:CoordinatorStatusUpdate,db:DbSession,user: Annotated[User, Depends(require_roles("ADMIN"))]): return coordinator_service.update_status(db,coordinator_id,payload,user=user)
@router.delete("/{coordinator_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_coordinator(coordinator_id:int,db:DbSession,user: Annotated[User, Depends(require_roles("ADMIN"))]): coordinator_service.delete_left(db,coordinator_id,user=user)

