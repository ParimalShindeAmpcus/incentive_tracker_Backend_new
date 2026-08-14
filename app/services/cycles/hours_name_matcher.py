"""Name-first Candidate Master matching for hours-template rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

NAME_AND_ID = "NAME_AND_ID"
ID_FALLBACK = "ID_FALLBACK"
NAME_ID_MISMATCH = "NAME_ID_MISMATCH"
UNMATCHED = "UNMATCHED"


def normalize_person_name(value: Optional[str]) -> str:
    return " ".join((value or "").split()).strip().casefold()


def normalize_candidate_id(value: Optional[str]) -> str:
    return (value or "").strip().upper()


@dataclass
class MasterCandidate:
    pk: int
    name: str
    external_id: str
    start_id: str = ""
    activity_id: str = ""


@dataclass
class HoursMatchRow:
    uploaded_name: str
    uploaded_id: str
    client: str = ""
    hours: float = 0
    month: str = ""
    source_row: int = 0


@dataclass
class MatchDecision:
    status: str
    master: Optional[MasterCandidate]
    reason: str
    warning: Optional[str] = None

    @property
    def matched(self) -> bool:
        return self.status in {NAME_AND_ID, ID_FALLBACK} and self.master is not None


def _ids_of(master: MasterCandidate) -> set[str]:
    return {
        normalize_candidate_id(master.external_id),
        normalize_candidate_id(master.start_id),
        normalize_candidate_id(master.activity_id),
    } - {""}


def build_name_index(masters: Sequence[MasterCandidate]) -> Dict[str, List[MasterCandidate]]:
    index: Dict[str, List[MasterCandidate]] = {}
    for master in masters:
        key = normalize_person_name(master.name)
        if not key:
            continue
        index.setdefault(key, []).append(master)
    return index


def build_id_index(masters: Sequence[MasterCandidate]) -> Dict[str, List[MasterCandidate]]:
    index: Dict[str, List[MasterCandidate]] = {}
    for master in masters:
        for ident in _ids_of(master):
            index.setdefault(ident, []).append(master)
    return index


def match_hours_row(
    row: HoursMatchRow,
    by_name: Dict[str, List[MasterCandidate]],
    by_id: Dict[str, List[MasterCandidate]],
) -> MatchDecision:
    name_key = normalize_person_name(row.uploaded_name)
    id_key = normalize_candidate_id(row.uploaded_id)
    name_hits = list(by_name.get(name_key, [])) if name_key else []

    if name_hits:
        if id_key:
            id_filtered = [m for m in name_hits if id_key in _ids_of(m)]
            if len(id_filtered) == 1:
                return MatchDecision(
                    status=NAME_AND_ID,
                    master=id_filtered[0],
                    reason="Candidate Name matched and Candidate ID belongs to the same Candidate Master record",
                )
            if not id_filtered:
                return MatchDecision(
                    status=NAME_ID_MISMATCH,
                    master=name_hits[0] if len(name_hits) == 1 else None,
                    reason="Candidate Name matched but Candidate ID does not match Candidate Master",
                )
        if len(name_hits) == 1 and not id_key:
            return MatchDecision(
                status=NAME_AND_ID,
                master=name_hits[0],
                reason="Candidate Name uniquely matched; uploaded Candidate ID was blank",
                warning="Candidate ID missing on hours row",
            )
        if len(name_hits) == 1 and id_key:
            return MatchDecision(
                status=NAME_ID_MISMATCH,
                master=name_hits[0],
                reason="Candidate Name matched but Candidate ID does not match Candidate Master",
            )
        return MatchDecision(
            status=UNMATCHED,
            master=None,
            reason="Candidate Name matched multiple Candidate Master records and Candidate ID could not disambiguate",
        )

    if id_key:
        id_hits = list(by_id.get(id_key, []))
        unique: List[MasterCandidate] = []
        seen = set()
        for master in id_hits:
            if master.pk in seen:
                continue
            seen.add(master.pk)
            unique.append(master)
        if len(unique) == 1:
            return MatchDecision(
                status=ID_FALLBACK,
                master=unique[0],
                reason="Candidate matched by Candidate ID because Candidate Name did not match",
                warning="Candidate matched by Candidate ID because Candidate Name did not match",
            )
        if len(unique) > 1:
            return MatchDecision(
                status=UNMATCHED,
                master=None,
                reason="Candidate ID matched multiple Candidate Master records",
            )

    return MatchDecision(
        status=UNMATCHED,
        master=None,
        reason="Candidate Name and Candidate ID could not be matched with Candidate Master",
    )
