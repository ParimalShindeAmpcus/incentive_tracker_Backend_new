"""Apply the approved client markup policy: python -m scripts.update_client_markup_masters."""
import json
from decimal import Decimal

from sqlalchemy.orm import Session
from prism.core.db import get_engine
from prism.repositories.entities.incentive_rules_master import IncentiveRuleMaster
from prism.services.common.seed_incentive_rules import _row
from prism.services.incentive_rules.client_markup_policy import MARKUP_SLABS, ELIGIBILITY


def update_client_markup_masters(db):
    existing = db.query(IncentiveRuleMaster).filter(
        IncentiveRuleMaster.division == "ampcusTechClient",
        IncentiveRuleMaster.rule_category == "MARKUP_SLAB",
    ).all()
    updated = 0
    for low, high, payouts in MARKUP_SLABS:
        matches = [rule for rule in existing
                   if Decimal(str(rule.markup_max)) == high
                   and Decimal(str(rule.markup_min)) in ({low, Decimal("5.01")} if low == 5 else {low})]
        if not matches:
            rule = IncentiveRuleMaster(**_row(division="ampcusTechClient", rule_category="MARKUP_SLAB"))
            db.add(rule)
            matches = [rule]
        for rule in matches:
            rule.markup_min = low
            rule.markup_max = high
            rule.role = None
            rule.amount = None
            rule.config_value = json.dumps(payouts)
            rule.description = ELIGIBILITY
            updated += 1
    db.flush()
    return updated


if __name__ == "__main__":
    with Session(get_engine()) as db:
        count = update_client_markup_masters(db)
        db.commit()
        print(f"Updated {count} Ampcus client markup master records.")
