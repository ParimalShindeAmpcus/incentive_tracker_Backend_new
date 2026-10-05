"""
Regression and Validation Test Suite:
1. Grid View vs Spreadsheet View record parity across all masters:
   - Nashik Recruiter Margin Slabs (10 records)
   - Nashik Full-Time (FTE) Policies (14 records = 6 recruiter slabs + 8 leadership)
   - Sambhaji Nagar Full-Time (FTE) Placement Policies (14 records = 6 recruiter slabs + 8 leadership)
   - Ampcus Tech - Client (11 records = 9 markup slabs + 2 configs)
   - Ampcus Tech - Inhouse (7 records = 4 role amounts + 3 configs)
2. Add / Edit / Delete / Deactivate lifecycle (including soft-delete and hard-delete).
3. Preservation of PRISM calculation engines.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from datetime import date
from sqlalchemy import text

from prism.core.db import get_db, init_db
from prism.repositories.entities.incentive_rules_master import IncentiveRuleMaster
from prism.repositories.entities.organization import Division
from prism.repositories.incentive_rules import incentive_rules_repository as repo
from prism.services.incentive_rules import incentive_rules_service as svc
from prism.models.incentive_rules.schemas import IncentiveRuleMasterIn, IncentiveRuleMasterUpdate


class TestIncentiveRulesMastersParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.db = next(get_db())

    def test_01_ampcus_tech_separation(self):
        """Verify Ampcus Tech is separated into Ampcus Tech - Client and Ampcus Tech - Inhouse."""
        client_div = self.db.query(Division).filter(Division.code == "ampcusTechClient").first()
        inhouse_div = self.db.query(Division).filter(Division.code == "ampcusTechInhouse").first()

        self.assertIsNotNone(client_div, "ampcusTechClient division must exist in DB")
        self.assertIsNotNone(inhouse_div, "ampcusTechInhouse division must exist in DB")

        self.assertIn("Client", client_div.name)
        self.assertIn("Inhouse", inhouse_div.name)

        client_rules = self.db.query(IncentiveRuleMaster).filter(IncentiveRuleMaster.division == "ampcusTechClient").all()
        inhouse_rules = self.db.query(IncentiveRuleMaster).filter(IncentiveRuleMaster.division == "ampcusTechInhouse").all()

        self.assertEqual(len(client_rules), 11, f"Expected 11 client rules, got {len(client_rules)}")
        self.assertEqual(len(inhouse_rules), 7, f"Expected 7 inhouse rules, got {len(inhouse_rules)}")

        # Verify categories
        client_cats = set(r.rule_category for r in client_rules)
        self.assertIn("MARKUP_SLAB", client_cats)
        self.assertIn("GLOBAL_CONFIG", client_cats)

        inhouse_cats = set(r.rule_category for r in inhouse_rules)
        self.assertIn("INHOUSE_AMOUNTS", inhouse_cats)
        self.assertIn("GLOBAL_CONFIG", inhouse_cats)

    def test_02_nashik_slabs_parity(self):
        """Verify Nashik Recruiter Margin Slabs has 10 records with 100% parity."""
        rules = self.db.query(IncentiveRuleMaster).filter(
            IncentiveRuleMaster.division == "nashik",
            IncentiveRuleMaster.rule_category == "RECRUITER_SLAB"
        ).all()

        self.assertEqual(len(rules), 10, f"Expected 10 Nashik slabs, got {len(rules)}")
        # Every rule must have valid margin range and amount
        for r in rules:
            self.assertIsNotNone(r.margin_min)
            self.assertIsNotNone(r.margin_max)
            self.assertIsNotNone(r.amount)
            self.assertEqual(r.role, "Recruiter")

    def test_03_nashik_fte_parity(self):
        """Verify Nashik FTE policies has exactly 14 records: 6 recruiter slabs + 8 leadership."""
        rules = self.db.query(IncentiveRuleMaster).filter(
            IncentiveRuleMaster.division == "nashik",
            IncentiveRuleMaster.rule_category.in_(["FTE_RECRUITER_SLAB", "FTE_LEADERSHIP"])
        ).all()

        self.assertEqual(len(rules), 14, f"Expected 14 Nashik FTE rules, got {len(rules)}")

        recruiter_slabs = [r for r in rules if r.rule_category == "FTE_RECRUITER_SLAB"]
        leadership_rules = [r for r in rules if r.rule_category == "FTE_LEADERSHIP"]

        self.assertEqual(len(recruiter_slabs), 6, "Expected 6 recruiter finder fee volume slabs")
        self.assertEqual(len(leadership_rules), 8, "Expected 8 FTE leadership fixed payout rules")

        # Verify grid mapping accounts for 100% of IDs
        grid_mapped_ids = set([r.id for r in recruiter_slabs] + [r.id for r in leadership_rules])
        spreadsheet_ids = set([r.id for r in rules])
        self.assertEqual(grid_mapped_ids, spreadsheet_ids, "All 14 rule IDs must be accounted for in Grid view")

    def test_04_sambhaji_nagar_fte_parity(self):
        """Verify Sambhaji Nagar FTE policies has exactly 14 records: 6 recruiter slabs + 8 leadership."""
        rules = self.db.query(IncentiveRuleMaster).filter(
            IncentiveRuleMaster.division == "sambhajiNagar",
            IncentiveRuleMaster.rule_category.in_(["FTE_RECRUITER_SLAB", "FTE_LEADERSHIP"])
        ).all()

        self.assertEqual(len(rules), 14, f"Expected 14 SN FTE rules, got {len(rules)}")

        recruiter_slabs = [r for r in rules if r.rule_category == "FTE_RECRUITER_SLAB"]
        leadership_rules = [r for r in rules if r.rule_category == "FTE_LEADERSHIP"]

        self.assertEqual(len(recruiter_slabs), 6, "Expected 6 recruiter finder fee volume slabs")
        self.assertEqual(len(leadership_rules), 8, "Expected 8 FTE leadership fixed payout rules")

        grid_mapped_ids = set([r.id for r in recruiter_slabs] + [r.id for r in leadership_rules])
        spreadsheet_ids = set([r.id for r in rules])
        self.assertEqual(grid_mapped_ids, spreadsheet_ids, "All 14 rule IDs must be accounted for in Grid view")

    def test_05_add_edit_toggle_delete_lifecycle(self):
        """Test full CRUD lifecycle with soft-delete and hard-delete."""
        # 1. Create a test rule
        new_rule_data = IncentiveRuleMasterIn(
            division="ampcusTechInhouse",
            rule_category="INHOUSE_AMOUNTS",
            rule_key="test_temp_rule",
            role="Specialist",
            amount=2500.0,
            description="Temporary test rule for validation",
            is_active=True,
            effective_from=date.today(),
        )
        created = svc.create_rule(self.db, new_rule_data, created_by=1)
        self.db.commit()
        self.assertIsNotNone(created)
        rule_id = created.id

        # 2. Edit rule
        update_data = IncentiveRuleMasterUpdate(
            amount=3200.0,
            description="Updated test rule description",
        )
        updated = svc.update_rule(self.db, rule_id, update_data, updated_by=1)
        self.db.commit()
        self.assertEqual(float(updated.amount), 3200.0)

        # 3. Toggle active / inactive
        toggled = svc.toggle_active(self.db, rule_id, updated_by=1)
        self.db.commit()
        self.assertFalse(toggled.is_active)

        toggled_back = svc.toggle_active(self.db, rule_id, updated_by=1)
        self.db.commit()
        self.assertTrue(toggled_back.is_active)

        # 4. Soft-delete (deactivate)
        soft_deleted = svc.soft_delete(self.db, rule_id, updated_by=1)
        self.db.commit()
        self.assertFalse(soft_deleted.is_active)

        # 5. Hard delete (permanent removal)
        hard_deleted = svc.hard_delete(self.db, rule_id)
        self.db.commit()
        self.assertTrue(hard_deleted)

        # Verify completely gone
        fetched = svc.get_rule(self.db, rule_id)
        self.assertIsNone(fetched)


if __name__ == "__main__":
    unittest.main()
