from typing import List, Optional, Set, Tuple

from app.utils.names import normalize_name


def find_duplicate_external_ids(rows: List[dict]) -> Set[str]:
    seen: Set[str] = set()
    dupes: Set[str] = set()
    for row in rows:
        key = (row.get("external_candidate_id") or "").strip().lower()
        if not key:
            continue
        if key in seen:
            dupes.add(key)
        seen.add(key)
    return dupes


def find_duplicate_name_client(rows: List[dict]) -> Set[Tuple[str, str]]:
    seen: Set[Tuple[str, str]] = set()
    dupes: Set[Tuple[str, str]] = set()
    for row in rows:
        key = (normalize_name(row.get("candidate_name")), normalize_name(row.get("client")))
        if not key[0]:
            continue
        if key in seen:
            dupes.add(key)
        seen.add(key)
    return dupes


def paid_dedupe_key(
    *,
    candidate_id: Optional[int],
    role: str,
    person: str,
    incentive_type: str,
) -> str:
    return f"{candidate_id or 'NA'}|{role}|{normalize_name(person)}|{incentive_type}"
