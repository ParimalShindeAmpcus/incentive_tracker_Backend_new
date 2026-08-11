"""Generic IncentiveCalculationService — selects strategy by division; params from slabs/benchmarks."""

from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.repositories import hours_repo, incentive_slab_repo
from app.services.calculation import ampcus_client, ampcus_inhouse, fulltime, nashik, sambhaji


class IncentiveCalculationService:
    STRATEGY_BY_DIVISION = {
        "nashik": "nashik",
        "sambhajiNagar": "sambhaji",
        "ampcusTechClient": "ampcus_client",
        "ampcusTechInhouse": "ampcus_inhouse",
        "fulltime": "fulltime",
    }

    def __init__(self, db: Session):
        self.db = db

    def get_benchmark(self, division: str) -> Decimal:
        row = hours_repo.get_benchmark(self.db, division)
        if row:
            return Decimal(str(row.benchmark_hours))
        return Decimal("160")

    def calculate_candidate(
        self,
        *,
        division: str,
        candidate: Dict[str, Any],
        hours: Decimal,
        recruiter_status: str = "ACTIVE",
        project_end: bool = False,
        placement_count: int = 1,
    ) -> List[Dict[str, Any]]:
        slabs = incentive_slab_repo.list_active(self.db, division=division)
        benchmark = self.get_benchmark(division)
        recruiter_payable = recruiter_status.upper() == "ACTIVE"
        project_ended_before = bool(project_end and hours < benchmark)
        strategy = self.STRATEGY_BY_DIVISION.get(division, "nashik")

        if strategy == "nashik":
            return nashik.calculate_nashik(
                candidate=candidate,
                hours=hours,
                benchmark=benchmark,
                slabs=slabs,
                project_ended_before_benchmark=project_ended_before,
                recruiter_payable=recruiter_payable,
            )
        if strategy == "sambhaji":
            return sambhaji.calculate_sambhaji(
                candidate=candidate,
                hours=hours,
                slabs=slabs,
                recruiter_payable=recruiter_payable,
            )
        if strategy == "ampcus_client":
            return ampcus_client.calculate_ampcus_client(
                candidate=candidate,
                slabs=slabs,
                recruiter_payable=recruiter_payable,
            )
        if strategy == "ampcus_inhouse":
            return ampcus_inhouse.calculate_ampcus_inhouse(
                candidate=candidate,
                slabs=slabs,
                recruiter_payable=recruiter_payable,
            )
        if strategy == "fulltime":
            return fulltime.calculate_fulltime(
                candidate=candidate,
                slabs=slabs,
                placement_count=placement_count,
                recruiter_payable=recruiter_payable,
            )
        return []


# Backwards-compatible alias expected by prompt
engine = IncentiveCalculationService
