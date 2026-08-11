from collections import defaultdict
from decimal import Decimal
from typing import Dict, Iterable


def aggregate_hours_by_candidate(rows: Iterable[dict]) -> Dict[int, Decimal]:
    totals: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    for row in rows:
        cid = row.get("candidate_id")
        if cid is None:
            continue
        hours = Decimal(str(row.get("hours_worked") or 0))
        totals[int(cid)] += hours
    return dict(totals)
