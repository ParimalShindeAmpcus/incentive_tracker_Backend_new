from datetime import date, datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def parse_flexible_date(v: Any) -> Optional[date]:
    """Helper validator to parse dates from various formats (strings, timestamps, datetime objects)."""
    if v is None or (isinstance(v, float) and str(v) == "nan"):
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()

    val_str = str(v).strip()
    if not val_str or val_str.lower() in ("nat", "none", "null", "nan"):
        return None

    # Common date formats used in JobDiva export files
    date_formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%m-%d-%Y",
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
    ]
    for fmt in date_formats:
        try:
            return datetime.strptime(val_str, fmt).date()
        except ValueError:
            continue

    # Attempt ISO format parsing fallback
    try:
        return datetime.fromisoformat(val_str).date()
    except Exception:
        pass

    return None


def clean_string(v: Any) -> Optional[str]:
    """Helper to trim whitespace and convert empty/nan strings to None."""
    if v is None:
        return None
    val_str = str(v).strip()
    if not val_str or val_str.lower() in ("nan", "none", "null"):
        return None
    return val_str


class JobDivaRecordSchema(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    activity_id: str = Field(..., description="Unique JobDiva Activity ID")
    position_type: Optional[str] = None
    candidate_full_name: Optional[str] = None
    candidate_email: Optional[EmailStr] = None
    candidate_city: Optional[str] = None
    candidate_state: Optional[str] = None
    candidate_mobile_phone: Optional[str] = None
    job_company: Optional[str] = None
    activity_date: Optional[date] = None
    jobdiva_ref_no: Optional[str] = None
    recruited_by: Optional[str] = None
    recruiter_email: Optional[EmailStr] = None
    job_title: Optional[str] = None
    work_city: Optional[str] = None
    work_state: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    end_client_name: Optional[str] = None
    work_authorization: Optional[str] = None
    organization_id: Optional[int] = None
    import_batch_id: Optional[int] = None
    raw_row_json: Optional[Dict[str, Any]] = None
    is_consumed: bool = False

    @field_validator("activity_id", mode="before")
    @classmethod
    def validate_activity_id(cls, v: Any) -> str:
        val = clean_string(v)
        if not val:
            raise ValueError("activity_id is required and cannot be empty")
        return val

    @field_validator(
        "position_type",
        "candidate_full_name",
        "candidate_email",
        "candidate_city",
        "candidate_state",
        "candidate_mobile_phone",
        "job_company",
        "jobdiva_ref_no",
        "recruited_by",
        "recruiter_email",
        "job_title",
        "work_city",
        "work_state",
        "end_client_name",
        "work_authorization",
        mode="before",
    )
    @classmethod
    def sanitize_strings(cls, v: Any) -> Optional[str]:
        return clean_string(v)

    @field_validator("activity_date", "start_date", "end_date", mode="before")
    @classmethod
    def validate_dates(cls, v: Any) -> Optional[date]:
        return parse_flexible_date(v)


class EmailImportLogSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: Optional[int] = None
    run_started_at: Optional[datetime] = None
    run_completed_at: Optional[datetime] = None
    mailbox: Optional[str] = None
    message_subject: Optional[str] = None
    attachment_name: Optional[str] = None
    total_rows: Optional[int] = 0
    inserted_rows: Optional[int] = 0
    duplicate_rows: Optional[int] = 0
    failed_rows: Optional[int] = 0
    error_detail: Optional[str] = None
    status: str = "RUNNING"
