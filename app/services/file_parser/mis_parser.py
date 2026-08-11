from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

import pandas as pd

from app.utils.dates import parse_date
from app.utils.names import normalize_client, normalize_name


def _col(df: pd.DataFrame, *aliases: str) -> Optional[str]:
    normalized = {_normalize(c): c for c in df.columns}
    for a in aliases:
        if a in normalized:
            return normalized[a]
    return None


def _normalize(value: Any) -> str:
    return str(value).strip().lower().replace("_", " ")


def _dec(value: Any) -> Optional[Decimal]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("$", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _str(value: Any) -> Optional[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def parse_mis_dataframe(df: pd.DataFrame) -> List[Dict[str, Any]]:
    id_col = _col(df, "candidate id", "candidateid", "start id", "startid", "id")
    name_col = _col(df, "candidate name", "candidate", "name")
    client_col = _col(df, "client", "end client", "customer")
    contract_col = _col(df, "contract type", "contract", "employment type")
    margin_col = _col(df, "margin", "margin/hr", "margin usd")
    start_col = _col(df, "start date", "startdate")
    recruiter_col = _col(df, "recruiter")
    tl_col = _col(df, "team lead", "teamlead", "tl")
    mgr_col = _col(df, "manager")
    sm_col = _col(df, "senior manager", "seniormanager")
    crm_col = _col(df, "crm")
    ad_col = _col(df, "associate director", "associatedirector")
    ch_col = _col(df, "center head", "centerhead")
    avp_col = _col(df, "avp")
    org_col = _col(df, "organization", "org")
    source_col = _col(df, "candidate source", "source")
    status_col = _col(df, "status")
    pay_col = _col(df, "pay rate", "payrate")
    bill_col = _col(df, "bill rate", "billrate")

    rows: List[Dict[str, Any]] = []
    for _, series in df.iterrows():
        name = _str(series[name_col]) if name_col else None
        ext_id = _str(series[id_col]) if id_col else None
        if not name and not ext_id:
            continue
        if name and normalize_name(name) in {"candidate name", "candidate", "name"}:
            continue
        client = _str(series[client_col]) if client_col else None
        rows.append(
            {
                "external_candidate_id": ext_id or normalize_name(name),
                "start_id": ext_id,
                "candidate_name": name or ext_id or "",
                "normalized_name": normalize_name(name or ext_id),
                "client": client,
                "normalized_client": normalize_client(client),
                "contract_type": _str(series[contract_col]) if contract_col else None,
                "margin": _dec(series[margin_col]) if margin_col else None,
                "pay_rate": _dec(series[pay_col]) if pay_col else None,
                "bill_rate": _dec(series[bill_col]) if bill_col else None,
                "start_date": parse_date(series[start_col]) if start_col else None,
                "recruiter": _str(series[recruiter_col]) if recruiter_col else None,
                "team_lead": _str(series[tl_col]) if tl_col else None,
                "manager": _str(series[mgr_col]) if mgr_col else None,
                "senior_manager": _str(series[sm_col]) if sm_col else None,
                "crm": _str(series[crm_col]) if crm_col else None,
                "associate_director": _str(series[ad_col]) if ad_col else None,
                "center_head": _str(series[ch_col]) if ch_col else None,
                "avp": _str(series[avp_col]) if avp_col else None,
                "organization": _str(series[org_col]) if org_col else None,
                "candidate_source": _str(series[source_col]) if source_col else None,
                "status": _str(series[status_col]) if status_col else None,
            }
        )
    return rows
