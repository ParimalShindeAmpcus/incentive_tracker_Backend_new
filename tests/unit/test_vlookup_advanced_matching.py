"""Edge-case tests for the enhanced entity-resolution matching layer."""

from __future__ import annotations

import pytest

from app.services.vlookup.normalization import extract_person_name, parse_name_tokens
from app.services.vlookup.parsers.client_hours import _extract_name_from_memo, aggregate_hours_by_candidate
from app.services.vlookup.reconciliation_matcher import ReconciliationMatcher
from app.services.vlookup.similarity import name_feature_scores


def _tpl(tid: int, name: str, client: str, month: str = "2025-08") -> dict:
    return {
        "id": tid,
        "candidate_id": f"C{tid}",
        "candidate_name": name,
        "client_name": client,
        "month": month,
        "hours": 0,
    }


def _group(name: str, client: str, month: str = "2025-08", hours: float = 40.0, **extra) -> dict:
    return {
        "candidate_name": name,
        "client_name": client,
        "month": month,
        "total_hours": hours,
        "weekly_breakdown": {f"{month}-01": hours},
        "source_rows": [],
        **extra,
    }


def _status_messy(results: dict, name: str) -> str:
    for status, rows in results.items():
        for row in rows:
            if row.get("messy_name_original") == name:
                return status
    raise AssertionError(f"No messy result for {name!r}")


def _status_tpl(results: dict, name: str) -> str:
    for status, rows in results.items():
        for row in rows:
            if row.get("template_candidate_name") == name:
                return status
    raise AssertionError(f"No template result for {name!r}")


@pytest.fixture
def matcher() -> ReconciliationMatcher:
    return ReconciliationMatcher()


class TestNameExtraction:
    def test_week_ending_memo(self):
        assert _extract_name_from_memo(
            "ABDEL BILEOMON FOR THE WEEK ENDING OF-06/21/2025"
        ).upper() == "ABDEL BILEOMON"

    def test_extract_person_name_strips_dates(self):
        assert extract_person_name("Anil Kumar FOR THE WEEK ENDING OF-06/21/2025").lower().startswith("anil")


class TestNameRepresentations:
    def test_compact_and_initials(self):
        parts = parse_name_tokens("Anil Kumar Sharma")
        assert parts["compact"] == "anilkumarsharma"
        assert parts["initials_str"] == "aks"
        assert parts["sorted_tokens"] == ["anil", "kumar", "sharma"]


class TestFeatureScores:
    def test_reordered_names_high_token_sort(self):
        features = name_feature_scores("Anil Kumar", "Kumar Anil")
        assert features["name_token_sort_similarity"] >= 99
        assert features["name_exact"] == 0 or features["name_token_sort_similarity"] >= 99

    def test_punctuation_compact(self):
        features = name_feature_scores("O'Connor", "OConnor")
        assert features["compact_match"] == 100.0


class TestAdvancedMatching:
    def test_name_order(self, matcher: ReconciliationMatcher):
        results = matcher.match(
            [_tpl(1, "Anil Kumar", "Abbott")],
            [_group("Kumar Anil", "Abbott:4215")],
            "2025-08",
        )
        assert _status_messy(results, "Kumar Anil") == "matched"

    def test_typo_last_name(self, matcher: ReconciliationMatcher):
        results = matcher.match(
            [_tpl(1, "Anil Kumar", "Abbott")],
            [_group("Anil Kumr", "Abbott:4215")],
            "2025-08",
        )
        assert _status_messy(results, "Anil Kumr") == "matched"

    def test_extra_tokens_subset(self, matcher: ReconciliationMatcher):
        results = matcher.match(
            [_tpl(1, "Anil Kumar", "Abbott")],
            [_group("Anil Kumar Sharma", "Abbott:4215")],
            "2025-08",
        )
        assert _status_messy(results, "Anil Kumar Sharma") in ("matched", "needs_review")
        assert _status_messy(results, "Anil Kumar Sharma") != "unmatched"

    def test_punctuation_variants(self, matcher: ReconciliationMatcher):
        templates = [_tpl(1, "O'Connor", "Abbott")]
        for messy in ["O Connor", "OConnor"]:
            results = matcher.match(templates, [_group(messy, "Abbott:4215")], "2025-08")
            assert _status_messy(results, messy) == "matched", messy

    def test_case_differences(self, matcher: ReconciliationMatcher):
        templates = [_tpl(1, "Anil Kumar", "Abbott")]
        for messy in ["ANIL KUMAR", "anil kumar", "Anil Kumar"]:
            results = matcher.match(templates, [_group(messy, "Abbott:4215")], "2025-08")
            assert _status_messy(results, messy) == "matched", messy

    def test_memo_noise(self, matcher: ReconciliationMatcher):
        results = matcher.match(
            [_tpl(1, "Anil Kumar", "Abbott")],
            [_group("ANIL KUMAR FOR THE WEEK ENDING OF-06/21/2025", "Abbott:4215")],
            "2025-08",
        )
        assert _status_tpl(results, "Anil Kumar") == "matched"

    def test_client_suffix(self, matcher: ReconciliationMatcher):
        results = matcher.match(
            [_tpl(1, "Anil Kumar", "Abbott")],
            [_group("Anil Kumar", "Abbott:4215")],
            "2025-08",
        )
        assert _status_messy(results, "Anil Kumar") == "matched"

    def test_ambiguous_same_name_same_client_goes_to_review(self, matcher: ReconciliationMatcher):
        results = matcher.match(
            [
                _tpl(1, "Rahul Kumar", "Abbott"),
                _tpl(2, "Rahul Kumar", "Abbott"),
            ],
            [_group("Rahul Kumar", "Abbott:4215")],
            "2025-08",
        )
        statuses = {_status_tpl(results, "Rahul Kumar")}
        assert "matched" not in statuses or any(
            r.get("match_status") == "needs_review"
            for rows in results.values()
            for r in rows
            if r.get("template_candidate_name") == "Rahul Kumar"
        )
        review_or_unmatched = [
            r["match_status"]
            for rows in results.values()
            for r in rows
            if r.get("template_candidate_name") == "Rahul Kumar"
        ]
        assert "needs_review" in review_or_unmatched
        assert review_or_unmatched.count("matched") <= 0

    def test_duplicate_master_name_does_not_look_unmatched(self, matcher: ReconciliationMatcher):
        """Two Hours Template IDs, one client-file person: neither should say 'not in file'."""
        results = matcher.match(
            [
                _tpl(1, "Rahul Kumar", "Outcomes", month="2025-06"),
                _tpl(2, "Rahul Kumar", "Outcomes", month="2025-06"),
            ],
            [
                _group(
                    "Rahul Kumar",
                    "Capital One",
                    month="2025-06",
                    hours=160.0,
                    monthly_hours={"2025-06": 160.0, "2025-07": 176.0},
                    weekly_by_month={
                        "2025-06": {"6/7/2025": 160.0},
                        "2025-07": {"7/5/2025": 176.0},
                    },
                )
            ],
            "2025-06",
        )
        rows = [
            r
            for rows in results.values()
            for r in rows
            if r.get("template_candidate_name") == "Rahul Kumar"
        ]
        assert len(rows) == 2
        statuses = {r["match_status"] for r in rows}
        assert "unmatched" not in statuses
        assert statuses <= {"needs_review", "conflicting"}
        with_hours = [r for r in rows if float(r.get("total_hours") or 0) > 0]
        without_hours = [r for r in rows if float(r.get("total_hours") or 0) == 0]
        assert len(with_hours) == 1
        assert len(without_hours) == 1
        flags = (without_hours[0].get("match_explanation") or {}).get("identity_flags") or []
        assert "identity_already_assigned" in flags
        assert without_hours[0].get("messy_name_original")

    def test_strong_name_conflicting_client(self, matcher: ReconciliationMatcher):
        results = matcher.match(
            [_tpl(1, "Anil Kumar", "Microsoft")],
            [_group("Anil Kumar", "Abbott:4215")],
            "2025-08",
        )
        assert _status_messy(results, "Anil Kumar") == "conflicting"

    def test_non_master_candidate_ignored(self, matcher: ReconciliationMatcher):
        results = matcher.match(
            [_tpl(1, "Anil Kumar", "Abbott")],
            [_group("Someone Else", "Abbott")],
            "2025-08",
        )
        assert _status_tpl(results, "Anil Kumar") == "unmatched"
        messy_names = {
            r.get("messy_name_original")
            for rows in results.values()
            for r in rows
            if r.get("messy_name_original")
        }
        assert "Someone Else" not in messy_names

    def test_weekly_rows_aggregate_to_one_identity(self):
        rows = [
            {"candidate_name": "Anil Kumar", "client_name": "Abbott", "hours_worked": 16, "week": "6/7/2025", "month": "2025-06", "source_ref": "ANIL-06/07"},
            {"candidate_name": "Anil Kumar", "client_name": "Abbott", "hours_worked": 40, "week": "6/14/2025", "month": "2025-06", "source_ref": "ANIL-06/14"},
            {"candidate_name": "Anil Kumar", "client_name": "Abbott", "hours_worked": 32, "week": "6/21/2025", "month": "2025-06", "source_ref": "ANIL-06/21"},
        ]
        groups = aggregate_hours_by_candidate(rows, group_by_month=False)
        assert len(groups) == 1
        assert groups[0]["total_hours"] == 88

    def test_generational_suffix_is_not_last_name(self):
        parts = parse_name_tokens("William Robert Galonek Jr")
        assert parts["last"] == "galonek"
        assert parts["suffix"] == "jr"
        assert parts["first"] == "william"

    def test_unrelated_jr_names_do_not_auto_match(self, matcher: ReconciliationMatcher):
        """Jr is not a surname; William * Jr people must not collapse together."""
        results = matcher.match(
            [_tpl(1, "William Robert Galonek Jr", "Frontier Communications")],
            [_group("William Douglas Wilson Jr", "FRONTIER")],
            "2025-08",
        )
        assert _status_tpl(results, "William Robert Galonek Jr") != "matched"
        ident = matcher._name_identity(
            "William Douglas Wilson Jr",
            "William Robert Galonek Jr",
        )
        assert ident["compatible"] is False

    def test_same_person_with_jr_still_matches(self, matcher: ReconciliationMatcher):
        results = matcher.match(
            [_tpl(1, "Harold A Smith Jr", "Verizon")],
            [_group("Harold A Smith Jr", "VERIZON")],
            "2025-08",
        )
        assert _status_tpl(results, "Harold A Smith Jr") == "matched"

    def test_match_explanation_includes_features(self, matcher: ReconciliationMatcher):
        results = matcher.match(
            [_tpl(1, "Anil Kumar", "Abbott")],
            [_group("Anil Kumar", "Abbott:4215")],
            "2025-08",
        )
        row = next(r for rows in results.values() for r in rows if r.get("messy_name_original") == "Anil Kumar")
        breakdown = (row.get("match_explanation") or {}).get("match_breakdown") or {}
        features = breakdown.get("name_features") or (row.get("match_explanation") or {}).get("signals", {}).get("name_features") or {}
        assert features.get("name_exact") == 100.0
        assert (row.get("match_explanation") or {}).get("audit", {}).get("reason")
