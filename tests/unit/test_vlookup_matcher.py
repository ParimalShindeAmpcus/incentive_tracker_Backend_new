"""Focused unit tests for client-gated VLOOKUP matching decisions."""

from __future__ import annotations

import pytest

from app.services.vlookup.normalization import normalize_client_name
from app.services.vlookup.reconciliation_matcher import ReconciliationMatcher
from app.services.vlookup.similarity import SimilarityScorer


def _tpl(
    tid: int,
    name: str,
    client: str,
    month: str = "2025-08",
    candidate_id: str = "",
) -> dict:
    return {
        "id": tid,
        "candidate_id": candidate_id or f"C{tid}",
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
        "weekly_breakdown": {"2025-08-01": hours},
        "source_rows": [],
        **extra,
    }


def _status_of(results: dict, messy_name: str) -> str:
    for status, rows in results.items():
        for row in rows:
            if row.get("messy_name_original") == messy_name:
                return status
    raise AssertionError(f"No result for {messy_name!r}")


def _status_of_template(results: dict, template_name: str) -> str:
    for status, rows in results.items():
        for row in rows:
            if row.get("template_candidate_name") == template_name:
                return status
    raise AssertionError(f"No template result for {template_name!r}")


def _row(results: dict, messy_name: str) -> dict:
    for rows in results.values():
        for row in rows:
            if row.get("messy_name_original") == messy_name:
                return row
    raise AssertionError(f"No result for {messy_name!r}")


def _all_messy_names(results: dict) -> set[str]:
    names = set()
    for rows in results.values():
        for row in rows:
            if row.get("messy_name_original"):
                names.add(row["messy_name_original"])
    return names


@pytest.fixture
def matcher() -> ReconciliationMatcher:
    return ReconciliationMatcher()


class TestClientNormalization:
    def test_colon_identifier_stripped(self):
        assert normalize_client_name("Abbott:4215") == "abbott"
        assert normalize_client_name("Abbott") == "abbott"

    def test_client_similarity_compatible(self):
        score = SimilarityScorer.client_similarity("Abbott", "Abbott:4215")
        assert score >= 88

    def test_client_similarity_mismatch(self):
        score = SimilarityScorer.client_similarity("Microsoft", "Abbott:4215")
        assert score <= 40


class TestDecisionMatrix:
    def test_exact_candidate_and_client_matched(self, matcher: ReconciliationMatcher):
        results = matcher.match(
            [_tpl(1, "John Smith", "Microsoft")],
            [_group("John Smith", "Microsoft")],
            target_month="2025-08",
        )
        assert _status_of(results, "John Smith") == "matched"
        row = _row(results, "John Smith")
        assert "client name is compatible" in (row["match_explanation"]["identity_summary"] or "").lower() or \
            "strongly matches" in (row["match_explanation"]["identity_summary"] or "").lower()

    def test_name_formatting_variants_matched(self, matcher: ReconciliationMatcher):
        templates = [_tpl(1, "Ram Bahal", "Abbott")]
        for messy in ["ram bahal", "RAM BAHAL", "Bahal, Ram"]:
            results = matcher.match(templates, [_group(messy, "Abbott:4215")], "2025-08")
            assert _status_of(results, messy) == "matched", messy

    def test_initial_variant_with_compatible_client(self, matcher: ReconciliationMatcher):
        results = matcher.match(
            [_tpl(1, "Ram Bahal", "Abbott")],
            [_group("R Bahal", "Abbott:4215")],
            "2025-08",
        )
        assert _status_of(results, "R Bahal") == "matched"

    def test_strong_name_wrong_client_is_conflicting(self, matcher: ReconciliationMatcher):
        results = matcher.match(
            [_tpl(1, "John Smith", "Microsoft")],
            [_group("John Smith", "Abbott:4215")],
            "2025-08",
        )
        assert _status_of(results, "John Smith") == "conflicting"
        row = _row(results, "John Smith")
        assert "conflict" in (row["match_explanation"]["identity_summary"] or "").lower()

    def test_strong_name_correct_client_matched(self, matcher: ReconciliationMatcher):
        results = matcher.match(
            [_tpl(1, "John Smith", "Microsoft")],
            [_group("John Smith", "Microsoft:1234")],
            "2025-08",
        )
        assert _status_of(results, "John Smith") == "matched"

    def test_no_candidate_unmatched(self, matcher: ReconciliationMatcher):
        results = matcher.match(
            [_tpl(1, "John Smith", "Microsoft")],
            [_group("Robert Patel", "Microsoft")],
            "2025-08",
        )
        assert _status_of_template(results, "John Smith") == "unmatched"
        assert "Robert Patel" not in _all_messy_names(results)

    def test_extra_client_people_are_ignored(self, matcher: ReconciliationMatcher):
        results = matcher.match(
            [_tpl(1, "John Smith", "Microsoft")],
            [
                _group("John Smith", "Microsoft"),
                _group("Someone Else", "Abbott"),
                _group("Not Ours", "Capital One"),
            ],
            "2025-08",
        )
        assert _status_of(results, "John Smith") == "matched"
        assert _all_messy_names(results) == {"John Smith"}
        assert sum(len(rows) for rows in results.values()) == 1

    def test_missing_client_goes_to_review_not_auto(self, matcher: ReconciliationMatcher):
        results = matcher.match(
            [_tpl(1, "John Smith", "Microsoft")],
            [_group("John Smith", "")],
            "2025-08",
        )
        assert _status_of(results, "John Smith") == "needs_review"

    def test_different_last_name_not_auto_matched(self, matcher: ReconciliationMatcher):
        results = matcher.match(
            [_tpl(1, "Ram Bahal", "Abbott")],
            [_group("Ram Patel", "Abbott")],
            "2025-08",
        )
        assert _status_of_template(results, "Ram Bahal") in ("unmatched", "needs_review")
        assert _status_of_template(results, "Ram Bahal") != "matched"

    def test_weekly_aggregation_preserved(self, matcher: ReconciliationMatcher):
        group = {
            "candidate_name": "John Smith",
            "client_name": "Microsoft",
            "month": "2025-06",
            "total_hours": 112,
            "weekly_breakdown": {
                "2025-06-07": 40,
                "2025-06-14": 40,
                "2025-06-21": 32,
            },
            "source_rows": [{}, {}, {}],
        }
        results = matcher.match(
            [_tpl(1, "John Smith", "Microsoft", month="2025-06")],
            [group],
            "2025-06",
        )
        row = _row(results, "John Smith")
        assert row["match_status"] == "matched"
        assert row["total_hours"] == 112
        assert len(row["weekly_breakdown"]) == 3

    def test_multiple_client_identities_claiming_one_master(self, matcher: ReconciliationMatcher):
        templates = [_tpl(1, "John Smith", "Microsoft")]
        groups = [
            _group("John Smith", "Microsoft", hours=40),
            _group("J Smith", "Microsoft", hours=32),
        ]
        results = matcher.match(templates, groups, "2025-08")
        # Template-master: exactly one Hours Template row is produced.
        assert sum(len(rows) for rows in results.values()) == 1
        assert _status_of_template(results, "John Smith") in (
            "matched",
            "needs_review",
            "potential_duplicate",
        )
        assert "Someone" not in _all_messy_names(results)
        matched_same = [
            r
            for rows in results.values()
            for r in rows
            if r.get("template_candidate_id") == 1 and r.get("match_status") == "matched"
        ]
        assert len(matched_same) <= 1

    def test_hours_do_not_force_identity(self, matcher: ReconciliationMatcher):
        results = matcher.match(
            [_tpl(1, "John Smith", "Microsoft")],
            [_group("Robert Patel", "Microsoft", hours=999)],
            "2025-08",
        )
        assert _status_of_template(results, "John Smith") == "unmatched"
        assert "Robert Patel" not in _all_messy_names(results)

    def test_alternatives_exclude_client_conflicts(self, matcher: ReconciliationMatcher):
        templates = [
            _tpl(1, "John Smith", "Microsoft"),
            _tpl(2, "John Smith", "Abbott"),
        ]
        results = matcher.match(
            templates,
            [_group("John Smith", "Microsoft")],
            "2025-08",
        )
        row = _row(results, "John Smith")
        assert row["match_status"] == "matched"
        for alt in row.get("alternatives") or []:
            # Abbott alternative should not appear as a "plausible" alt when client conflicts
            assert "abbott" not in str(alt.get("client_name") or "").lower()

    def test_name_alone_never_auto_matches_with_available_wrong_client(
        self, matcher: ReconciliationMatcher
    ):
        """Regression: old engine floored confidence to ~name*0.9 and auto-matched."""
        results = matcher.match(
            [_tpl(1, "Jeneria Chonice Hopkins", "DOMINION ENERGY")],
            [_group("Jeneria Chonice Hopkins", "COMPLETELY DIFFERENT CLIENT LLC")],
            "2025-08",
        )
        assert _status_of(results, "Jeneria Chonice Hopkins") == "conflicting"

    def test_audit_contains_required_fields(self, matcher: ReconciliationMatcher):
        results = matcher.match(
            [_tpl(1, "John Smith", "Microsoft")],
            [_group("John Smith", "Microsoft:99")],
            "2025-08",
        )
        row = _row(results, "John Smith")
        audit = row["match_explanation"]["audit"]
        assert audit.get("master_candidate")
        assert audit.get("client_candidate")
        assert audit.get("candidate_similarity") is not None
        assert audit.get("final_confidence") is not None
        assert audit.get("reason") or audit.get("why")

    def test_invoice_prefix_does_not_match_unrelated_people(self, matcher: ReconciliationMatcher):
        results = matcher.match(
            [_tpl(1, "John Smith", "Microsoft")],
            [_group("Robert Patel", "Microsoft", invoice_prefixes=["SMIT"])],
            "2025-08",
        )
        assert _status_of_template(results, "John Smith") == "unmatched"

    def test_multi_month_hours_stay_on_one_identity(self, matcher: ReconciliationMatcher):
        groups = [
            _group("John Smith", "Microsoft", month="2025-06", hours=40),
            _group("John Smith", "Microsoft", month="2025-07", hours=80),
            _group("John Smith", "Microsoft", month="2025-08", hours=32),
        ]
        results = matcher.match(
            [_tpl(1, "John Smith", "Microsoft", month="2025-08")],
            groups,
            "2025-08",
        )
        assert sum(len(rows) for rows in results.values()) == 1
        row = _row(results, "John Smith")
        assert row["match_status"] == "matched"
        monthly = row.get("monthly_hours") or {}
        assert monthly.get("2025-06") == 40
        assert monthly.get("2025-07") == 80
        assert monthly.get("2025-08") == 32
