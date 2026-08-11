"""Health request/response DTOs."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
