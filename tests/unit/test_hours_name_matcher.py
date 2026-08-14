from app.services.cycles.hours_name_matcher import (
    ID_FALLBACK,
    NAME_AND_ID,
    NAME_ID_MISMATCH,
    UNMATCHED,
    HoursMatchRow,
    MasterCandidate,
    build_id_index,
    build_name_index,
    match_hours_row,
)


def _indexes(masters):
    return build_name_index(masters), build_id_index(masters)


def test_name_and_id_both_match():
    master = MasterCandidate(pk=1, name="Aisha Mayes", external_id="12345", start_id="12345")
    by_name, by_id = _indexes([master])
    decision = match_hours_row(
        HoursMatchRow(uploaded_name="  aisha   mayes ", uploaded_id="12345"),
        by_name,
        by_id,
    )
    assert decision.status == NAME_AND_ID
    assert decision.matched
    assert decision.master.pk == 1


def test_name_matches_id_does_not():
    master = MasterCandidate(pk=1, name="Aisha Mayes", external_id="12345")
    by_name, by_id = _indexes([master])
    decision = match_hours_row(
        HoursMatchRow(uploaded_name="Aisha Mayes", uploaded_id="99999"),
        by_name,
        by_id,
    )
    assert decision.status == NAME_ID_MISMATCH
    assert not decision.matched
    assert "Candidate ID does not match" in decision.reason


def test_id_fallback_when_name_differs():
    master = MasterCandidate(pk=1, name="Aisha Mayes", external_id="12345")
    by_name, by_id = _indexes([master])
    decision = match_hours_row(
        HoursMatchRow(uploaded_name="Aisha Mays", uploaded_id="12345"),
        by_name,
        by_id,
    )
    assert decision.status == ID_FALLBACK
    assert decision.matched
    assert "Candidate Name did not match" in (decision.warning or "")


def test_neither_name_nor_id_matches():
    master = MasterCandidate(pk=1, name="Aisha Mayes", external_id="12345")
    by_name, by_id = _indexes([master])
    decision = match_hours_row(
        HoursMatchRow(uploaded_name="Unknown Candidate", uploaded_id="UNKNOWN123"),
        by_name,
        by_id,
    )
    assert decision.status == UNMATCHED
    assert not decision.matched
