from typing import Any, Dict, List, Optional

import pandas as pd

from app.utils.dates import parse_date
from app.utils.names import normalize_name


def _col(df: pd.DataFrame, *aliases: str) -> Optional[str]:
    normalized = {str(c).strip().lower().replace("_", " "): c for c in df.columns}
    for a in aliases:
        if a in normalized:
            return normalized[a]
    return None


def parse_project_end_dataframe(df: pd.DataFrame) -> List[Dict[str, Any]]:
    id_col = _col(df, "candidate id", "start id", "id")
    name_col = _col(df, "candidate name", "candidate", "name")
    date_col = _col(df, "project end date", "end date", "project end")
    source_col = _col(df, "source", "project end source")
    rows: List[Dict[str, Any]] = []
    for _, series in df.iterrows():
        name = str(series[name_col]).strip() if name_col and not pd.isna(series[name_col]) else None
        cand_id = str(series[id_col]).strip() if id_col and not pd.isna(series[id_col]) else None
        if not name and not cand_id:
            continue
        if name and normalize_name(name) in {"candidate name", "candidate", "name"}:
            continue
        rows.append(
            {
                "candidate_id": cand_id,
                "candidate_name": name,
                "project_end_date": parse_date(series[date_col]) if date_col else None,
                "project_end": True,
                "project_end_source": (
                    str(series[source_col]).strip() if source_col and not pd.isna(series[source_col]) else "UPLOAD"
                ),
            }
        )
    return rows
