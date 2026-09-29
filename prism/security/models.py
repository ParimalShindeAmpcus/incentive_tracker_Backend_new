"""Security domain models stub."""

from pydantic import BaseModel


class SecurityFinding(BaseModel):
    code: str
    message: str
