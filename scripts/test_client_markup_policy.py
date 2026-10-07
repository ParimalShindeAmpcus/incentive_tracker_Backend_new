import json
import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from prism.services.common.seed_incentive_rules import _build_seed_rows
from prism.services.cycles.engines.ampcus_client import resolve_slab
from prism.services.incentive_rules.client_markup_policy import MARKUP_SLABS, PAYOUT_ROLES
from prism.services.incentive_rules.rule_loader import _atc_hardcoded_defaults
from scripts.update_client_markup_masters import update_client_markup_masters


class ClientMarkupPolicyTests(unittest.TestCase):
    def test_reference_rates_and_boundaries(self):
        expected = [
            ("0", (0, 0, 0, 0, 0)),
            ("5", (0, 0, 0, 0, 0)),
            ("5.01", (2000, 250, 500, 750, 500)),
            ("10", (2000, 250, 500, 750, 500)),
            ("10.01", (3000, 250, 500, 750, 1000)),
            ("15.01", (5000, 500, 1000, 1000, 1500)),
            ("20.01", (6000, 500, 1000, 1500, 2000)),
            ("25.01", (7000, 500, 1000, 1500, 2500)),
            ("30.01", (8000, 500, 1000, 1500, 3000)),
            ("35.01", (9000, 500, 1000, 1500, 3500)),
            ("40.01", (10000, 500, 1000, 1500, 4000)),
            ("100", (10000, 500, 1000, 1500, 4000)),
        ]
        for config in (None, _atc_hardcoded_defaults()):
            for markup, amounts in expected:
                with self.subTest(markup=markup, config=config is not None):
                    rates = resolve_slab(Decimal(markup), config)[2]
                    self.assertEqual(tuple(rates[role] for role in PAYOUT_ROLES), amounts)
                    self.assertEqual(rates["Center Head"], rates["CH/VP"])
            self.assertIsNone(resolve_slab(Decimal("100.01"), config))

    def test_seed_contains_five_policy_roles_per_range(self):
        rows = [r for r in _build_seed_rows() if r["division"] == "ampcusTechClient" and r["rule_category"] == "MARKUP_SLAB"]
        self.assertEqual(len(rows), 9)
        for row, (low, high, rates) in zip(rows, MARKUP_SLABS):
            self.assertEqual((row["markup_min"], row["markup_max"]), (low, high))
            self.assertEqual(json.loads(row["config_value"]), rates)

    def test_update_is_repeatable_and_preserves_status(self):
        db = MagicMock()
        records = []
        db.query.return_value.filter.return_value.all.side_effect = lambda: list(records)
        db.add.side_effect = records.append
        update_client_markup_masters(db)
        records[1].markup_min = Decimal("5.01")
        records[1].is_active = False
        update_client_markup_masters(db)
        self.assertEqual(len(records), 9)
        self.assertEqual(records[1].markup_min, Decimal("5"))
        self.assertFalse(records[1].is_active)
