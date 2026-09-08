"""Confirm Consolidated File did not replace Smart Match name-identity logic.

These cases reuse the previous matcher rules (normalize, first/last, initials,
token order, punctuation, RapidFuzz blend) against Consolidated-style groups:
empty client_name + Organisation.
"""

from __future__ import annotations

from app.services.vlookup.normalization import normalize_name, parse_name_tokens
from app.services.vlookup.reconciliation_matcher import ReconciliationMatcher


def _tpl(tid: int, name: str, client: str = "Infosys", month: str = "2025-06") -> dict:
    return {
        "id": tid,
        "candidate_id": f"C{tid}",
        "candidate_name": name,
        "client_name": client,
        "month": month,
        "hours": 0,
    }


def _consolidated(name: str, org: str = "Bravens Inc", hours: float = 160.0) -> dict:
    return {
        "candidate_name": name,
        "client_name": "",
        "organisation": org,
        "month": "",
        "total_hours": hours,
        "weekly_breakdown": {"New Hours": hours},
        "source_rows": [],
    }


def _status_of(results: dict, messy_name: str) -> str:
    for status, rows in results.items():
        for row in rows:
            if row.get("messy_name_original") == messy_name:
                return status
    raise AssertionError(f"No result for {messy_name!r}")


def test_name_identity_is_not_exact_string_only():
    matcher = ReconciliationMatcher()
    ident = matcher._name_identity("BRIJESH   KUMAR DUBEY", "Brijesh Kumar Dubey")
    assert ident["compatible"] is True
    assert ident["score"] == 100.0
    assert ident["method"] == "exact"
    assert normalize_name("BRIJESH   KUMAR DUBEY") == normalize_name("Brijesh Kumar Dubey")
    assert "BRIJESH   KUMAR DUBEY" != "Brijesh Kumar Dubey"


def test_punctuation_compact_and_last_first_order():
    matcher = ReconciliationMatcher()
    compact = matcher._name_identity("O'Connor", "OConnor")
    assert compact["compatible"] is True
    assert compact["method"] == "compact"

    ordered = matcher._name_identity("Dubey, Brijesh Kumar", "Brijesh Kumar Dubey")
    assert ordered["compatible"] is True
    assert ordered["method"] in ("exact", "token_permutation")
    assert ordered["score"] >= 99.0


def test_initial_and_middle_name_variants():
    matcher = ReconciliationMatcher()
    initial = matcher._name_identity("B Dubey", "Brijesh Kumar Dubey")
    assert initial["compatible"] is True
    assert initial["method"] in ("initial_variant", "first_last", "containment", "token_subset")
    assert initial["score"] >= 78.0

    middle = matcher._name_identity("Brijesh Dubey", "Brijesh Kumar Dubey")
    assert middle["compatible"] is True
    assert middle["method"] in ("first_last", "containment", "token_subset")


def test_unrelated_names_still_rejected():
    matcher = ReconciliationMatcher()
    ident = matcher._name_identity("Ram Patel", "Ram Bahal")
    assert ident["compatible"] is False
    assert ident["method"] == "rejected_unrelated"


def test_consolidated_groups_keep_name_variant_matches():
    matcher = ReconciliationMatcher()
    templates = [_tpl(1, "Brijesh Kumar Dubey")]
    variants = [
        "brijesh kumar dubey",
        "BRIJESH KUMAR DUBEY",
        "Brijesh  Kumar   Dubey",
        "Dubey, Brijesh Kumar",
        "Brijesh Kumar Dubey.",
    ]
    for messy in variants:
        results = matcher.match(templates, [_consolidated(messy)], "2025-06")
        assert _status_of(results, messy) == "matched", messy


def test_token_thresholds_unchanged():
    matcher = ReconciliationMatcher()
    assert matcher.AUTO_MATCH_THRESHOLD == 88.0
    assert matcher.REVIEW_THRESHOLD == 70.0
    assert matcher.MIN_IDENTITY_NAME_SCORE == 70.0
    assert matcher.STRONG_NAME_SCORE == 90.0
    assert matcher.FIRST_NAME_FUZZY_MIN == 85.0
    assert matcher.LAST_NAME_FUZZY_MIN == 88.0


def test_parse_name_tokens_still_splits_middle_and_initials():
    parts = parse_name_tokens("Brijesh K Dubey")
    assert parts["first"] == "brijesh"
    assert parts["last"] == "dubey"
    assert parts["middle"] == ["k"]
    assert parts["initials"] == ["k"]
