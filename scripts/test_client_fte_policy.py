"""Run with python -m unittest scripts.test_client_fte_policy."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from prism.services.common.seed_incentive_rules import _client_fte_rows, _seed_missing_client_fte_rules
from prism.services.cycles.engines.ampcus_client import ATC_FTE_FIXED, _fte_recruiter_amount


class ClientFtePolicyTests(unittest.TestCase):
    def test_recruiter_amounts_are_per_placement_for_calendar_month_volume(self):
        for above, amounts in [(False, (15000, 18000, 20000)), (True, (20000, 25000, 30000))]:
            for count, expected in zip((1, 2, 3, 6), (*amounts, amounts[2])):
                self.assertEqual(_fte_recruiter_amount(above, count), expected)

    def test_seeded_policy_matches_engine_and_has_only_requested_fixed_roles(self):
        rows = _client_fte_rows("ampcusTechClient")
        self.assertEqual(len(rows), 11)
        for row in rows:
            if row["rule_category"] == "FTE_RECRUITER_SLAB":
                self.assertEqual(row["amount"], _fte_recruiter_amount(row["finder_fee_above"], row["placement_count_min"]))
        fixed = {r["role"]: r["amount"] for r in rows if r["rule_category"] == "FTE_LEADERSHIP"}
        self.assertEqual(fixed, {"Team Lead": 1000, "Manager": 1500, "CRM": 1500, "Associate Director": 4000, "Center Head": 4000})
        self.assertEqual(fixed, ATC_FTE_FIXED)

    def test_backfill_preserves_existing_slots_and_is_idempotent(self):
        db = MagicMock()
        existing = [SimpleNamespace(rule_category="FTE_RECRUITER_SLAB", role="Recruiter", finder_fee_above=False, placement_count_min=1, amount=12345, is_active=False)]
        db.query.return_value.filter.return_value.all.side_effect = lambda: list(existing)
        db.add.side_effect = existing.append
        _seed_missing_client_fte_rules(db)
        self.assertEqual(db.add.call_count, 10)
        self.assertEqual(existing[0].amount, 12345)
        self.assertFalse(existing[0].is_active)
        _seed_missing_client_fte_rules(db)
        self.assertEqual(db.add.call_count, 10)


if __name__ == "__main__":
    unittest.main()
