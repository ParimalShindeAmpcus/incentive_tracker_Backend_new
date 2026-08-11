from dataclasses import dataclass
from typing import List, Optional, Sequence

from app.models.candidate import Candidate
from app.utils.names import normalize_client, normalize_name


@dataclass
class MatchInput:
    candidate_id: Optional[str] = None
    candidate_name: Optional[str] = None
    client: Optional[str] = None
    source_row_ref: Optional[str] = None


@dataclass
class MatchOutcome:
    candidate: Optional[Candidate]
    match_method: str
    match_result: str
    confidence: str


def _id_index(candidates: Sequence[Candidate]) -> dict[str, Candidate]:
    index: dict[str, Candidate] = {}
    for c in candidates:
        if c.external_candidate_id:
            index[c.external_candidate_id.strip().lower()] = c
        if c.start_id:
            index[c.start_id.strip().lower()] = c
    return index


def _name_client_index(candidates: Sequence[Candidate]) -> dict[tuple[str, str], List[Candidate]]:
    index: dict[tuple[str, str], List[Candidate]] = {}
    for c in candidates:
        key = (c.normalized_name, c.normalized_client or "")
        index.setdefault(key, []).append(c)
    return index


def match_row(row: MatchInput, candidates: Sequence[Candidate]) -> MatchOutcome:
    """Priority: (1) candidate/start ID (2) normalized name + client (3) name only (4) unmatched.

    Fuzzy matches are returned as LOW_CONFIDENCE and must not be auto-accepted for calc.
    """
    by_id = _id_index(candidates)
    if row.candidate_id:
        hit = by_id.get(row.candidate_id.strip().lower())
        if hit:
            return MatchOutcome(hit, "CANDIDATE_ID", "MATCHED", "HIGH")

    name = normalize_name(row.candidate_name)
    client = normalize_client(row.client)
    if name:
        by_nc = _name_client_index(candidates)
        hits = by_nc.get((name, client), [])
        if len(hits) == 1:
            return MatchOutcome(hits[0], "NAME_CLIENT", "MATCHED", "HIGH")
        if len(hits) > 1:
            return MatchOutcome(hits[0], "NAME_CLIENT", "DUPLICATE", "MEDIUM")

        name_only = [c for c in candidates if c.normalized_name == name]
        if len(name_only) == 1:
            return MatchOutcome(name_only[0], "NAME_ONLY", "MATCHED", "MEDIUM")
        if len(name_only) > 1:
            return MatchOutcome(name_only[0], "NAME_ONLY", "DUPLICATE", "LOW")

        # Safe fuzzy: exact token containment / prefix — never HIGH
        for c in candidates:
            if name and c.normalized_name and (
                name in c.normalized_name or c.normalized_name in name
            ):
                return MatchOutcome(c, "FUZZY_NAME", "LOW_CONFIDENCE", "LOW")

    return MatchOutcome(None, "NONE", "UNMATCHED", "NONE")


def match_many(rows: List[MatchInput], candidates: Sequence[Candidate]) -> List[MatchOutcome]:
    return [match_row(r, candidates) for r in rows]
