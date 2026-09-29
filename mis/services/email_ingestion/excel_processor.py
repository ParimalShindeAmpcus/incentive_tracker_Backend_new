from pathlib import Path
from typing import Dict, List, Tuple
import pandas as pd
from loguru import logger
from pydantic import ValidationError

from mis.schemas.jobdiva import JobDivaRecordSchema

# Column alias dictionary for flexible JobDiva Excel header mapping
COLUMN_HEADER_MAP = {
    "activity_id": [
        "activity id", "activity id#", "activity_id", "activityid",
        "activity #", "act id", "id"
    ],
    "position_type": ["position type", "position_type", "type", "job type"],
    "candidate_full_name": [
        "candidate full name", "candidate name", "candidate",
        "candidate_full_name", "full name"
    ],
    "candidate_email": ["candidate email", "candidate email address", "candidate_email", "email"],
    "candidate_city": ["candidate city", "candidate_city", "candidate home city", "city"],
    "candidate_state": ["candidate state", "candidate_state", "candidate home state", "state"],
    "candidate_mobile_phone": [
        "candidate mobile phone", "candidate phone", "mobile phone",
        "phone", "candidate_mobile_phone", "candidate cell"
    ],
    "job_company": ["job company", "company", "company name", "job_company"],
    "activity_date": ["activity date", "activity_date", "date"],
    "jobdiva_ref_no": [
        "jobdiva ref no", "jobdiva ref #", "ref #", "jobdiva_ref_no",
        "ref no", "reference number", "job ref #"
    ],
    "recruited_by": ["recruited by", "recruiter", "recruited_by", "recruiter name"],
    "recruiter_email": ["recruiter email", "recruiter email address", "recruiter_email", "recruited by email"],
    "job_title": ["job title", "title", "job_title", "position title"],
    "work_city": ["work city", "work_city", "job city", "city 1"],
    "work_state": ["work state", "work_state", "job state", "state 1"],
    "start_date": ["start date", "start_date"],
    "end_date": ["end date", "end_date"],
    "end_client_name": ["end client name", "end client", "end_client_name", "client"],
    "work_authorization": ["work authorization", "work auth", "work_authorization", "authorization"],
}


def normalize_header(header: str) -> str:
    """Clean and normalize a header string for alias matching."""
    if not header or not isinstance(header, str):
        return ""
    h = header.strip().lower()
    h = h.replace("_", " ").replace("#", " ").replace(".", " ")
    h = " ".join(h.split())
    return h


def build_column_mapping(df_columns: List[str]) -> Dict[str, str]:
    """Build a mapping from Excel column names to JobDivaRecordSchema field names."""
    mapping = {}
    normalized_headers = {col: normalize_header(str(col)) for col in df_columns}

    for schema_field, aliases in COLUMN_HEADER_MAP.items():
        for col_orig, col_norm in normalized_headers.items():
            if col_orig in mapping:
                continue
            if col_norm in aliases or col_norm.replace(" ", "_") in aliases:
                mapping[col_orig] = schema_field
                break

    return mapping


def process_jobdiva_excel(file_path: str) -> Tuple[List[Dict], int, int, int]:
    """
    Read an Excel attachment, map columns to JobDiva schema, and validate each row.
    Returns: (valid_records, total_rows, valid_count, failed_count)
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Excel file not found at: {file_path}")

    logger.info(f"Processing Excel file: '{path.name}'...")

    try:
        # Read Excel file into DataFrame
        df = pd.read_excel(file_path, engine="openpyxl")
    except Exception as e:
        logger.error(f"Failed to parse Excel file '{path.name}': {e}")
        raise ValueError(f"Could not read Excel file format: {e}")

    total_rows = len(df)
    if total_rows == 0:
        logger.warning(f"Excel file '{path.name}' is empty.")
        return [], 0, 0, 0

    col_mapping = build_column_mapping(list(df.columns))
    logger.info(f"Mapped {len(col_mapping)} column(s) from Excel headers: {col_mapping}")

    # Check if activity_id was mapped
    if "activity_id" not in col_mapping.values():
        # Fallback: look for any column containing 'activity' or 'id'
        for col in df.columns:
            norm = normalize_header(str(col))
            if "activity" in norm or norm in ("id", "ref"):
                col_mapping[col] = "activity_id"
                logger.info(f"Fallback mapping: mapped '{col}' to 'activity_id'.")
                break

    # Rename mapped columns
    df_renamed = df.rename(columns=col_mapping)

    valid_records = []
    failed_count = 0

    for idx, row in df_renamed.iterrows():
        raw_dict = row.to_dict()

        # Convert NaN values to None
        cleaned_dict = {}
        for k, v in raw_dict.items():
            if pd.isna(v):
                cleaned_dict[k] = None
            else:
                cleaned_dict[k] = v

        # Build schema payload with raw row json backup
        row_payload = {k: v for k, v in cleaned_dict.items() if k in JobDivaRecordSchema.model_fields}
        row_payload["raw_row_json"] = {str(k): (None if pd.isna(v) else str(v)) for k, v in raw_dict.items()}

        try:
            record = JobDivaRecordSchema(**row_payload)
            valid_records.append(record.model_dump())
        except ValidationError as ve:
            failed_count += 1
            logger.warning(f"Row {idx + 1} validation failed in '{path.name}': {ve}")

    valid_count = len(valid_records)
    logger.info(
        f"Excel processing complete for '{path.name}': {total_rows} total, "
        f"{valid_count} valid, {failed_count} failed."
    )

    return valid_records, total_rows, valid_count, failed_count
