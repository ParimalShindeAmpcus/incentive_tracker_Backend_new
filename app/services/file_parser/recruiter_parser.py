from typing import Any, Dict, List, Optional

import pandas as pd

from app.models.recruiter import RecruiterStatusEnum
from app.utils.names import normalize_name


def _col(df: pd.DataFrame, *aliases: str) -> Optional[str]:
    normalized = {str(c).strip().lower().replace("_", " "): c for c in df.columns}
    for a in aliases:
        if a in normalized:
            return normalized[a]
    return None


def _parse_status(value: Any) -> RecruiterStatusEnum:
    text = str(value or "").strip().upper()
    if "LEFT" in text or text in {"INACTIVE", "EXIT"}:
        return RecruiterStatusEnum.LEFT
    if "NOTICE" in text or "NP" == text:
        return RecruiterStatusEnum.NOTICE
    return RecruiterStatusEnum.ACTIVE


def parse_recruiter_dataframe(df: pd.DataFrame) -> List[Dict[str, Any]]:
    name_col = _col(df, "recruiter", "name", "employee", "employee name")
    status_col = _col(df, "status", "recruiter status")
    month_col = _col(df, "month", "effective month", "incentive month")
    rows: List[Dict[str, Any]] = []
    for _, series in df.iterrows():
        name = str(series[name_col]).strip() if name_col and not pd.isna(series[name_col]) else None
        if not name or normalize_name(name) in {"recruiter", "name", "employee"}:
            continue
        month = None
        if month_col and not pd.isna(series[month_col]):
            month = str(series[month_col]).strip()[:7]
        rows.append(
            {
                "recruiter_name": name,
                "normalized_name": normalize_name(name),
                "status": _parse_status(series[status_col] if status_col else "ACTIVE"),
                "effective_month": month,
            }
        )
    return rows
