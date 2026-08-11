"""Hours data + benchmarks HTTP routes."""

from typing import List, Optional

from fastapi import APIRouter, Query

from app.models.hours.schemas import (
    CreateHoursVersionRequest,
    HoursBenchmarkOut,
    HoursBenchmarkUpdate,
    HoursVersionDetail,
    VersionMetaOut,
)
from app.services.common.deps import CurrentUser, DbSession
from app.services.hours import hours_service

router = APIRouter()
benchmarks_router = APIRouter()


@router.get("/versions", response_model=List[VersionMetaOut])
def list_versions(db: DbSession, division: Optional[str] = Query(None)) -> List[VersionMetaOut]:
    return hours_service.list_versions(db, division=division)


@router.get("/versions/{version_id}", response_model=HoursVersionDetail)
def get_version(version_id: int, db: DbSession) -> HoursVersionDetail:
    return hours_service.get_version_detail(db, version_id)


@router.post("/versions", response_model=HoursVersionDetail)
def create_version(
    payload: CreateHoursVersionRequest,
    db: DbSession,
    user: CurrentUser,
) -> HoursVersionDetail:
    return hours_service.create_version(db, payload, uploaded_by=user.id)


@benchmarks_router.get("", response_model=List[HoursBenchmarkOut])
def list_benchmarks(db: DbSession) -> List[HoursBenchmarkOut]:
    return hours_service.list_benchmarks(db)


@benchmarks_router.put("/{division}", response_model=HoursBenchmarkOut)
def put_benchmark(
    division: str,
    payload: HoursBenchmarkUpdate,
    db: DbSession,
    user: CurrentUser,
) -> HoursBenchmarkOut:
    return hours_service.update_benchmark(db, division, payload, updated_by=user.id)
