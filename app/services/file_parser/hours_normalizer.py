from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

import pandas as pd

from app.utils.dates import month_key, parse_date
from app.utils.names import normalize_name


CANDIDATE_ID_ALIASES = {
    "candidate id",
    "candidate_id",
    "start id",
    "start_id",
    "startid",
    "id",
}
NAME_ALIASES = {"candidate", "candidate name", "candidate_name", "name", "consultant"}
HOURS_ALIASES = {"hours", "hours worked", "hours_worked", "quantity", "qty", "total hours"}
DATE_ALIASES = {"date", "work date", "work_date", "week ending", "week_ending", "month"}
CLIENT_ALIASES = {"client", "customer", "end client"}


def _norm_col(col: Any) -> str:
    return str(col).strip().lower()


def _pick(columns: List[str], aliases: set[str]) -> Optional[str]:
    for c in columns:
        if _norm_col(c) in aliases:
            return c
    return None


def _to_decimal(value: Any) -> Decimal:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return Decimal("0")
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return Decimal("0")


def normalize_hours_dataframe(df: pd.DataFrame) -> List[Dict[str, Any]]:
    cols = list(df.columns)
    id_col = _pick(cols, CANDIDATE_ID_ALIASES)
    name_col = _pick(cols, NAME_ALIASES)
    hours_col = _pick(cols, HOURS_ALIASES)
    date_col = _pick(cols, DATE_ALIASES)
    client_col = _pick(cols, CLIENT_ALIASES)

    rows: List[Dict[str, Any]] = []
    for idx, series in df.iterrows():
        hours = _to_decimal(series[hours_col]) if hours_col else Decimal("0")
        if hours == 0 and not (id_col or name_col):
            continue
        name = str(series[name_col]).strip() if name_col and not pd.isna(series[name_col]) else None
        if name and normalize_name(name) in {"candidate", "candidate name", "name"}:
            continue
        work_date = parse_date(series[date_col]) if date_col else None
        cand_id = None
        if id_col and not pd.isna(series[id_col]):
            cand_id = str(series[id_col]).strip()
        client = None
        if client_col and not pd.isna(series[client_col]):
            client = str(series[client_col]).strip()
        rows.append(
            {
                "source_row": int(idx) + 2 if isinstance(idx, int) else None,
                "candidate_id": cand_id,
                "candidate_name": name,
                "client": client,
                "work_date": work_date,
                "month_key": month_key(work_date),
                "hours_worked": hours,
            }
        )
    return rows


def read_tabular_upload(content: bytes, filename: str) -> pd.DataFrame:
    name = (filename or "").lower()
    from io import BytesIO

    bio = BytesIO(content)
    if name.endswith(".csv"):
        return pd.read_csv(bio)
    return pd.read_excel(bio)
