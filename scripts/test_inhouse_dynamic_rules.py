"""
Regression & Unit Test Suite for Dynamic Inhouse Rules & Validation Messages.
Verifies:
1. Default Inhouse rules parity (Recruiter, Manager, Center Head).
2. Dynamic tenure milestone message & reason code adaptation (e.g. min_days=60 -> INHOUSE_60_DAY_REQUIREMENT_NOT_MET).
3. Dynamic candidate hierarchy roles (Team Lead, CRM, Senior Manager, etc.) configured in IncentiveRuleMaster.
4. Exceeded max roles enforcement with dynamic multi-role setup.
"""

import os
import sys
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from prism.core.db import get_engine, init_db
from prism.repositories.entities.incentive_rules_master import IncentiveRuleMaster
from prism.services.incentive_rules.rule_loader import InhouseRuleConfig, load_inhouse_config
from prism.services.cycles.engines.ampcus_inhouse import calculate_placement
from prism.services.cycles.cycle_engine import run_cycle_calculation
from prism.services.incentives.nashik_calculator import CycleWindow


class TestInhouseDynamicRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.engine = get_engine()

    def setUp(self):
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()

    def test_01_default_config_loading(self):
        """Verify load_inhouse_config loads default 7 rules and maps role_amounts."""
        cfg = load_inhouse_config(self.db)
        self.assertEqual(cfg.min_days, 90)
        self.assertEqual(cfg.min_start_date, date(2025, 7, 1))
        self.assertEqual(cfg.max_roles_per_person, 2)
        self.assertEqual(cfg.recruiter_below_manager, 3000)
        self.assertEqual(cfg.recruiter_above_manager, 5000)
        self.assertEqual(cfg.manager_amount, 500)
        self.assertGreater(cfg.center_head_amount, 0)
        self.assertIn("Recruiter", cfg.role_amounts)
        self.assertIn("Manager", cfg.role_amounts)
        self.assertIn("Center Head", cfg.role_amounts)

    def test_02_dynamic_tenure_validation_and_message(self):
        """Verify dynamic min_days changes both calculation reason and validation summary message."""
        cand_50d = SimpleNamespace(
            id=101,
            candidate_name="Candidate 50Days",
            start_date=date(2025, 10, 11),
            job_level="Below Manager",
            recruiter="John Recruiter",
            manager="Bob Manager",
            center_head="Alice Head",
            status="ACTIVE",
            is_active=True,
            incentive_active=True,
            end_date=None,
            start_id="S-101",
            external_candidate_id="EXT-101",
            contract_type="Full Time",
            organization="Ampcus Tech In-House",
        )
        cycle_end = date(2025, 11, 30)  # Exactly 50 days tenure

        # With default 90 days:
        cfg90 = load_inhouse_config(self.db)
        lines90 = calculate_placement(cand_50d, cycle_end=cycle_end, coordinators={}, rule_config=cfg90)
        self.assertTrue(all(not l.eligible for l in lines90))
        self.assertEqual(lines90[0].reason, "INHOUSE_90_DAY_REQUIREMENT_NOT_MET")

        # With dynamic 45 days:
        cfg45 = InhouseRuleConfig(min_days=45, role_amounts={"Recruiter": 3000, "Manager": 500, "Center Head": 1000})
        lines45 = calculate_placement(cand_50d, cycle_end=cycle_end, coordinators={}, rule_config=cfg45)
        self.assertTrue(all(l.eligible for l in lines45))
        self.assertEqual(lines45[0].amount, Decimal("3000"))

        # With dynamic 60 days (cand has 50 days -> should fail with INHOUSE_60_DAY_REQUIREMENT_NOT_MET):
        cfg60 = InhouseRuleConfig(min_days=60, role_amounts={"Recruiter": 3000, "Manager": 500, "Center Head": 1000})
        lines60 = calculate_placement(cand_50d, cycle_end=cycle_end, coordinators={}, rule_config=cfg60)
        self.assertTrue(all(not l.eligible for l in lines60))
        self.assertEqual(lines60[0].reason, "INHOUSE_60_DAY_REQUIREMENT_NOT_MET")

    def test_03_dynamic_roles_support(self):
        """Verify candidate hierarchy roles like Team Lead, CRM, Senior Manager are evaluated when present in master."""
        cand_multi = SimpleNamespace(
            id=102,
            candidate_name="Full Hierarchy Candidate",
            start_date=date(2025, 8, 1),
            job_level="Above Manager",
            recruiter="Recruiter One",
            manager="Manager Two",
            center_head="Head Three",
            team_lead="Lead Four",
            crm="CRM Five",
            senior_manager="Senior Six",
            status="ACTIVE",
            is_active=True,
            incentive_active=True,
            end_date=None,
            start_id="S-102",
            external_candidate_id="EXT-102",
            contract_type="Full Time",
            organization="Ampcus Tech In-House",
        )
        cycle_end = date(2025, 11, 30)

        # Config with additional roles: Team Lead (1500), CRM (1000), Senior Manager (2000)
        cfg_custom = InhouseRuleConfig(
            min_days=90,
            recruiter_above_manager=5000,
            role_amounts={
                "Recruiter": 5000,
                "Manager": 500,
                "Center Head": 1000,
                "Team Lead": 1500,
                "CRM": 1000,
                "Senior Manager": 2000,
            },
        )
        lines = calculate_placement(cand_multi, cycle_end=cycle_end, coordinators={}, rule_config=cfg_custom)
        roles_output = {l.role: l for l in lines}

        self.assertIn("Team Lead", roles_output)
        self.assertIn("CRM", roles_output)
        self.assertIn("Senior Manager", roles_output)

        self.assertEqual(roles_output["Team Lead"].person, "Lead Four")
        self.assertEqual(roles_output["Team Lead"].amount, Decimal("1500"))
        self.assertTrue(roles_output["Team Lead"].eligible)

        self.assertEqual(roles_output["CRM"].person, "CRM Five")
        self.assertEqual(roles_output["CRM"].amount, Decimal("1000"))
        self.assertTrue(roles_output["CRM"].eligible)

        self.assertEqual(roles_output["Senior Manager"].person, "Senior Six")
        self.assertEqual(roles_output["Senior Manager"].amount, Decimal("2000"))
        self.assertTrue(roles_output["Senior Manager"].eligible)

    def test_04_max_roles_limiting_with_dynamic_roles(self):
        """Verify that when 1 person holds 3+ roles across dynamic roles, only top max_roles are approved."""
        cand_same_person = SimpleNamespace(
            id=103,
            candidate_name="Dual Role Candidate",
            start_date=date(2025, 8, 1),
            job_level="Above Manager",
            recruiter="Same Person",    # 5000
            team_lead="Same Person",    # 1500
            manager="Same Person",      # 500
            center_head="Head Different", # 1000
            status="ACTIVE",
            is_active=True,
            incentive_active=True,
            end_date=None,
            start_id="S-103",
            external_candidate_id="EXT-103",
            contract_type="Full Time",
            organization="Ampcus Tech In-House",
        )
        cycle_end = date(2025, 11, 30)

        cfg = InhouseRuleConfig(
            min_days=90,
            max_roles_per_person=2,
            role_amounts={
                "Recruiter": 5000,
                "Team Lead": 1500,
                "Manager": 500,
                "Center Head": 1000,
            },
        )
        lines = calculate_placement(cand_same_person, cycle_end=cycle_end, coordinators={}, rule_config=cfg)
        lines_by_role = {l.role: l for l in lines}

        # Top 2 roles for 'Same Person' are Recruiter (5000) and Team Lead (1500).
        # Manager (500) must be excluded per EXCEEDED_MAX_ROLES!
        self.assertTrue(lines_by_role["Recruiter"].eligible)
        self.assertEqual(lines_by_role["Recruiter"].amount, Decimal("5000"))

        self.assertTrue(lines_by_role["Team Lead"].eligible)
        self.assertEqual(lines_by_role["Team Lead"].amount, Decimal("1500"))

        self.assertFalse(lines_by_role["Manager"].eligible)
        self.assertEqual(lines_by_role["Manager"].reason, "EXCEEDED_MAX_ROLES")
        self.assertEqual(lines_by_role["Manager"].amount, Decimal("0"))

    def test_05_min_start_date_policy_cutoff(self):
        """Verify placements starting prior to min_start_date are strictly excluded."""
        cycle_end = date(2025, 12, 31)
        cfg = InhouseRuleConfig(
            min_start_date=date(2025, 7, 1),
            min_days=90,
            role_amounts={"Recruiter": 3000, "Manager": 500, "Center Head": 1000},
        )

        # Candidate joining before cutoff (June 15, 2025 - 199 days tenure, but before July 1, 2025)
        cand_prior = SimpleNamespace(
            id=201,
            candidate_name="Prior Placement",
            start_date=date(2025, 6, 15),
            job_level="Below Manager",
            recruiter="Recruiter A",
            manager="Manager B",
            center_head="Head C",
            status="ACTIVE",
            is_active=True,
            incentive_active=True,
            end_date=None,
            start_id="S-201",
            contract_type="Full Time",
            organization="Ampcus Tech In-House",
        )
        lines_prior = calculate_placement(cand_prior, cycle_end=cycle_end, coordinators={}, rule_config=cfg)
        self.assertTrue(all(not l.eligible for l in lines_prior))
        self.assertEqual(lines_prior[0].reason, "INHOUSE_STARTED_BEFORE_POLICY_DATE")

        # Also test with string and datetime start_date
        cand_str = SimpleNamespace(
            id=202,
            candidate_name="String Date Candidate",
            start_date="2025-06-15T00:00:00",
            job_level="Below Manager",
            recruiter="Recruiter A",
            manager="Manager B",
            center_head="Head C",
            status="ACTIVE",
            is_active=True,
            incentive_active=True,
            end_date=None,
            start_id="S-202",
            contract_type="Full Time",
            organization="Ampcus Tech In-House",
        )
        lines_str = calculate_placement(cand_str, cycle_end=cycle_end, coordinators={}, rule_config=cfg)
        self.assertEqual(lines_str[0].reason, "INHOUSE_STARTED_BEFORE_POLICY_DATE")

        # Candidate joining on or after cutoff (July 15, 2025 - 169 days tenure)
        cand_valid = SimpleNamespace(
            id=203,
            candidate_name="Valid Policy Placement",
            start_date=date(2025, 7, 15),
            job_level="Below Manager",
            recruiter="Recruiter A",
            manager="Manager B",
            center_head="Head C",
            status="ACTIVE",
            is_active=True,
            incentive_active=True,
            end_date=None,
            start_id="S-203",
            contract_type="Full Time",
            organization="Ampcus Tech In-House",
        )
        lines_valid = calculate_placement(cand_valid, cycle_end=cycle_end, coordinators={}, rule_config=cfg)
        self.assertTrue(all(l.eligible for l in lines_valid))
        self.assertEqual(lines_valid[0].reason, "ELIGIBLE")


if __name__ == "__main__":
    unittest.main()
