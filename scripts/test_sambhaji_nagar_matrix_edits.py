import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from decimal import Decimal
from prism.core.db import get_db, init_db
from prism.models.incentive_rules.schemas import (
    IncentiveRuleMasterIn,
    IncentiveRuleMasterUpdate,
)
from prism.repositories.entities.incentive_rules_master import IncentiveRuleMaster
from prism.services.cycles.engines.sambhaji_nagar import matrix_amount
from prism.services.incentive_rules import incentive_rules_service as svc
from prism.services.incentive_rules.rule_loader import load_sn_config


class TestSambhajiNagarMatrixEdits(unittest.TestCase):
    def setUp(self):
        init_db()
        self.db = next(get_db())

    def tearDown(self):
        self.db.close()

    def test_01_add_row_and_calculate(self):
        """Test adding a brand new margin tier ($70.01 - $90.00) and verifying calculation."""
        # 1. Create 5 rules for the new tier
        hour_ranges = [
            (Decimal("0"), Decimal("40"), Decimal("8000")),
            (Decimal("41"), Decimal("80"), Decimal("10000")),
            (Decimal("81"), Decimal("120"), Decimal("12000")),
            (Decimal("121"), Decimal("160"), Decimal("15000")),
            (Decimal("161"), Decimal("99999"), Decimal("30000")),
        ]

        created_ids = []
        try:
            payloads = [
                IncentiveRuleMasterIn(
                    division="sambhajiNagar",
                    rule_category="RECRUITER_SLAB",
                    role="Recruiter",
                    margin_min=Decimal("70.01"),
                    margin_max=Decimal("90.00"),
                    hours_min=h_min,
                    hours_max=h_max,
                    amount=amt,
                    is_active=True,
                    description=f"SN recruiter: margin $70.01–$90.00, hours {h_min}–{h_max}h",
                )
                for h_min, h_max, amt in hour_ranges
            ]

            created = svc.batch_create_rules(self.db, payloads, created_by=1)
            created_ids = [r.id for r in created]
            self.assertEqual(len(created_ids), 5)

            # 2. Verify config loads new dynamic rules
            cfg = load_sn_config(self.db)
            self.assertTrue(len(cfg.matrix_rules) > 0)

            # 3. Test calculation for margin $75.00 with 30 hours -> should be 8000
            amt_30h = matrix_amount(Decimal("75.00"), Decimal("30"), rule_config=cfg)
            self.assertEqual(amt_30h, 8000, f"Expected 8000 for $75 margin 30h, got {amt_30h}")

            # Test calculation for margin $75.00 with 100 hours -> should be 12000
            amt_100h = matrix_amount(Decimal("75.00"), Decimal("100"), rule_config=cfg)
            self.assertEqual(amt_100h, 12000, f"Expected 12000 for $75 margin 100h, got {amt_100h}")

            # Test calculation for margin $75.00 with 180 hours -> should be 30000
            amt_180h = matrix_amount(Decimal("75.00"), Decimal("180"), rule_config=cfg)
            self.assertEqual(amt_180h, 30000, f"Expected 30000 for $75 margin 180h, got {amt_180h}")

        finally:
            # Clean up
            if created_ids:
                svc.batch_delete_rules(self.db, created_ids, hard=True)

    def test_02_edit_hours_and_margin_ranges(self):
        """Test editing margin range and hours range and verifying calculation."""
        # Find $1.00 - $3.00, 0-40h rule
        rule = (
            self.db.query(IncentiveRuleMaster)
            .filter(
                IncentiveRuleMaster.division == "sambhajiNagar",
                IncentiveRuleMaster.rule_category == "RECRUITER_SLAB",
                IncentiveRuleMaster.hours_min == 0,
                IncentiveRuleMaster.margin_min == Decimal("1.00"),
            )
            .first()
        )
        self.assertIsNotNone(rule)
        orig_margin_max = rule.margin_max
        orig_hours_max = rule.hours_max
        orig_amount = rule.amount

        try:
            # Edit margin_max to 3.20, hours_max to 45, and amount to 550
            svc.update_rule(
                self.db,
                rule.id,
                IncentiveRuleMasterUpdate(
                    margin_max=Decimal("3.20"),
                    hours_max=Decimal("45"),
                    amount=Decimal("550"),
                ),
                updated_by=1,
            )
            self.db.commit()

            cfg = load_sn_config(self.db)

            # Test margin $3.15 with 42 hours (was previously outside 40h) -> should get 550
            amt = matrix_amount(Decimal("3.15"), Decimal("42"), rule_config=cfg)
            self.assertEqual(amt, 550, f"Expected 550 for $3.15 margin 42h, got {amt}")

        finally:
            # Restore
            svc.update_rule(
                self.db,
                rule.id,
                IncentiveRuleMasterUpdate(
                    margin_max=orig_margin_max,
                    hours_max=orig_hours_max,
                    amount=orig_amount,
                ),
                updated_by=1,
            )
            self.db.commit()


if __name__ == "__main__":
    unittest.main()
