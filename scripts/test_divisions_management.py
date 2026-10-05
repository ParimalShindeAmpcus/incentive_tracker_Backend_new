import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from prism.core.db import get_engine
from prism.models.organization.schemas import DivisionCreate, DivisionUpdate
from prism.services.organization import organization_service
from prism.services.incentive_rules.rule_loader import load_nashik_config, load_sn_config


class TestDivisionManagement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = get_engine()

    def setUp(self):
        self.db = Session(self.engine)
        # Clean up any leftover test data
        self.db.execute(text("DELETE FROM incentive_rule_master WHERE division = 'test_pune'"))
        self.db.execute(text("DELETE FROM divisions WHERE code = 'test_pune'"))
        self.db.commit()

    def tearDown(self):
        self.db.execute(text("DELETE FROM incentive_rule_master WHERE division = 'test_pune'"))
        self.db.execute(text("DELETE FROM divisions WHERE code = 'test_pune'"))
        self.db.commit()
        self.db.close()

    def test_01_list_divisions(self):
        """Verify list_divisions retrieves all divisions with aggregated rule counts."""
        divs = organization_service.list_divisions(self.db)
        self.assertGreaterEqual(len(divs), 4)
        codes = [d.code for d in divs]
        self.assertIn("nashik", codes)
        self.assertIn("sambhajiNagar", codes)
        self.assertIn("ampcusTechClient", codes)
        self.assertIn("ampcusTechInhouse", codes)

        nashik_div = next(d for d in divs if d.code == "nashik")
        self.assertGreater(nashik_div.rules_count, 0)
        self.assertGreater(nashik_div.active_rules_count, 0)

    def test_02_duplicate_validations(self):
        """Verify duplicate name and duplicate code validation."""
        # 1. Existing code
        with self.assertRaises(HTTPException) as ctx:
            organization_service.create_division(
                self.db,
                DivisionCreate(name="Unique Name", code="nashik")
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("cycle code 'nashik' already exists", ctx.exception.detail)

        # 2. Existing name
        with self.assertRaises(HTTPException) as ctx:
            organization_service.create_division(
                self.db,
                DivisionCreate(name="Nashik Division", code="unique_code")
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("name 'Nashik Division' already exists", ctx.exception.detail)

    def test_03_create_division_with_seed_rules(self):
        """Verify creating a new division auto-seeds baseline rules and returns DTO."""
        div = organization_service.create_division(
            self.db,
            DivisionCreate(
                name="Test Pune Division",
                code="test_pune",
                description="Custom test division for Pune branch.",
                calculation_engine="MARGIN_SLABS_PRO_RATA",
                is_active=True,
                seed_default_rules=True,
            )
        )
        self.assertEqual(div.code, "test_pune")
        self.assertEqual(div.name, "Test Pune Division")
        self.assertGreater(div.rules_count, 20)

        # Verify dynamic rule loader picks up the new division rules
        cfg = load_nashik_config(self.db, division="test_pune")
        self.assertGreater(len(cfg.recruiter_slabs), 0)
        self.assertEqual(cfg.standard_hours, Decimal("160"))

    def test_04_toggle_and_update_division(self):
        """Verify update and toggle operations."""
        div = organization_service.create_division(
            self.db,
            DivisionCreate(
                name="Test Pune Division",
                code="test_pune",
                calculation_engine="MARGIN_SLABS_PRO_RATA",
                is_active=True,
                seed_default_rules=False,
            )
        )
        # Toggle
        toggled = organization_service.toggle_division(self.db, div.id)
        self.assertFalse(toggled.is_active)

        toggled_back = organization_service.toggle_division(self.db, div.id)
        self.assertTrue(toggled_back.is_active)

        # Update
        updated = organization_service.update_division(
            self.db,
            div.id,
            DivisionUpdate(
                name="Test Pune Division Renamed",
                description="Updated description",
                calculation_engine="MARGIN_HOURS_MATRIX",
            )
        )
        self.assertEqual(updated.name, "Test Pune Division Renamed")
        self.assertEqual(updated.calculation_engine, "MARGIN_HOURS_MATRIX")
        self.assertEqual(updated.description, "Updated description")

    def test_05_core_division_protection(self):
        """Verify standard system divisions cannot be deleted."""
        nashik_div = organization_service.list_divisions(self.db)
        nashik_id = next(d.id for d in nashik_div if d.code == "nashik")

        with self.assertRaises(HTTPException) as ctx:
            organization_service.delete_division(self.db, nashik_id)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("standard core system division", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
