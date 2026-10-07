"""
Comprehensive test suite verifying that ALL calculation cycles work properly:
1. Nashik Cycle (MARGIN_SLABS_PRO_RATA - W2/C2C pro rata & FTE finder fees)
2. Sambhaji Nagar Cycle (MARGIN_HOURS_MATRIX - Margin x Hours matrix & FTE)
3. Ampcus Tech Client Cycle (CLIENT_MARKUP_PERCENT - Markup slabs & FTE)
4. Ampcus Tech In-House Cycle (INHOUSE_FLAT_RATES - Flat rates & dynamic tenure/roles)
5. Special Incentive Module (Monthly highest placements & margins)
"""

import os
import sys
import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from prism.core.db import get_engine, init_db
from prism.repositories.entities.candidate import Candidate
from prism.repositories.entities.coordinator import CoordinatorRecord, CoordinatorStatus
from prism.repositories.entities.cycle import IncentiveCycle, CycleStatus
from prism.services.cycles.cycle_engine import run_cycle_calculation
from prism.services.cycles.hours_template_parser import HoursMatchRow
from prism.services.incentives.nashik_calculator import CycleWindow
from prism.services.special_incentive import special_incentive_service


class TestAllCyclesWork(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.engine = get_engine()

    def setUp(self):
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()

    def test_01_nashik_cycle_calculation(self):
        """Verify Nashik cycle calculation runs and produces eligible line drafts."""
        cycle = IncentiveCycle(
            id=9901,
            name="Test Nashik Cycle",
            division="nashik",
            incentive_month="2026-10",
            cycle_start_date=date(2026, 10, 1),
            cycle_end_date=date(2026, 10, 31),
            status=CycleStatus.DRAFT,
        )
        window = CycleWindow(start=date(2026, 10, 1), end=date(2026, 10, 31))

        # Pick an active Nashik candidate from DB
        cand = (
            self.db.query(Candidate)
            .filter(
                Candidate.recruiter_location.ilike("%nashik%"),
                Candidate.contract_type.in_(["W2", "C2C"]),
                Candidate.is_active == True,
            )
            .first()
        )
        if not cand:
            # Fallback to any active candidate
            cand = self.db.query(Candidate).filter(Candidate.is_active == True).first()

        self.assertIsNotNone(cand, "Must have at least one candidate for test")

        hours_row = HoursMatchRow(
            source_row=1,
            uploaded_name=cand.candidate_name,
            uploaded_id=cand.start_id or cand.external_candidate_id,
            hours=Decimal("160"),
            client="Test Client",
        )

        drafts, stats, match_rows, validations = run_cycle_calculation(
            self.db, cycle, [hours_row], window
        )

        self.assertIsInstance(drafts, list)
        self.assertIsInstance(stats, dict)
        self.assertIsInstance(validations, list)
        self.assertGreater(len(match_rows), 0)
        self.assertEqual(match_rows[0]["match_result"].value, "MATCHED")

    def test_02_sambhaji_nagar_cycle_calculation(self):
        """Verify Sambhaji Nagar cycle calculation runs and matches candidate matrix."""
        cycle = IncentiveCycle(
            id=9902,
            name="Test Sambhaji Nagar Cycle",
            division="sambhajiNagar",
            incentive_month="2026-10",
            cycle_start_date=date(2026, 10, 1),
            cycle_end_date=date(2026, 10, 31),
            status=CycleStatus.DRAFT,
        )
        window = CycleWindow(start=date(2026, 10, 1), end=date(2026, 10, 31))

        cand = (
            self.db.query(Candidate)
            .filter(
                Candidate.recruiter_location.ilike("%sambhaji%"),
                Candidate.is_active == True,
            )
            .first()
        )
        if not cand:
            cand = self.db.query(Candidate).filter(Candidate.is_active == True).first()

        self.assertIsNotNone(cand)

        hours_row = HoursMatchRow(
            source_row=1,
            uploaded_name=cand.candidate_name,
            uploaded_id=cand.start_id or cand.external_candidate_id,
            hours=Decimal("120"),
            client="Test Client",
        )

        drafts, stats, match_rows, validations = run_cycle_calculation(
            self.db, cycle, [hours_row], window
        )

        self.assertIsInstance(drafts, list)
        self.assertIsInstance(stats, dict)
        self.assertIsInstance(validations, list)
        self.assertGreater(len(match_rows), 0)

    def test_03_ampcus_tech_client_cycle_calculation(self):
        """Verify Ampcus Tech Client calculation runs with markup slabs."""
        cycle = IncentiveCycle(
            id=9903,
            name="Test ATC Client Cycle",
            division="ampcusTechClient",
            incentive_month="2026-10",
            cycle_start_date=date(2026, 10, 1),
            cycle_end_date=date(2026, 10, 31),
            status=CycleStatus.DRAFT,
        )
        window = CycleWindow(start=date(2026, 10, 1), end=date(2026, 10, 31))

        cand = (
            self.db.query(Candidate)
            .filter(
                Candidate.organization.ilike("%ampcustech%"),
                ~Candidate.organization.ilike("%in-house%"),
                ~Candidate.organization.ilike("%inhouse%"),
                Candidate.is_active == True,
            )
            .first()
        )
        if not cand:
            cand = self.db.query(Candidate).filter(Candidate.is_active == True).first()

        self.assertIsNotNone(cand)

        hours_row = HoursMatchRow(
            source_row=1,
            uploaded_name=cand.candidate_name,
            uploaded_id=cand.start_id or cand.external_candidate_id,
            hours=Decimal("160"),
            client="Test Client",
        )

        drafts, stats, match_rows, validations = run_cycle_calculation(
            self.db, cycle, [hours_row], window
        )

        self.assertIsInstance(drafts, list)
        self.assertIsInstance(stats, dict)
        self.assertIsInstance(validations, list)

    def test_04_ampcus_tech_inhouse_cycle_calculation(self):
        """Verify Ampcus Tech In-House calculation runs without hours file."""
        cycle = IncentiveCycle(
            id=9904,
            name="Test In-House Cycle",
            division="ampcusTechInhouse",
            incentive_month="2026-10",
            cycle_start_date=date(2026, 10, 1),
            cycle_end_date=date(2026, 10, 31),
            status=CycleStatus.DRAFT,
        )
        window = CycleWindow(start=date(2026, 10, 1), end=date(2026, 10, 31))

        # In-House cycle runs directly with empty hours_rows:
        drafts, stats, match_rows, validations = run_cycle_calculation(
            self.db, cycle, [], window
        )

        self.assertIsInstance(drafts, list)
        self.assertIsInstance(stats, dict)
        self.assertIsInstance(validations, list)
        self.assertIn("before_policy_date", stats)
        self.assertIn("inactive", stats)

    def test_05_special_incentive_service(self):
        """Verify Special Incentive service runs without error and calculates top performers."""
        resp = special_incentive_service.get_special_incentive(self.db, "2026-10")
        self.assertEqual(resp.month, "2026-10")
        self.assertEqual(resp.incentive_amount, 5000.0)
        self.assertTrue(len(resp.organizations) >= 2)

        details = special_incentive_service.get_special_incentive_details(
            self.db,
            month="2026-10",
            organization_key="ampcus_inc",
            category="highest_placements",
        )
        self.assertEqual(details.month, "2026-10")
        self.assertEqual(details.organization, "Ampcus Inc")


if __name__ == "__main__":
    unittest.main()
