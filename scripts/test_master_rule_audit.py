"""Regression checks for transactional incentive master auditing."""
import unittest
from decimal import Decimal
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from prism.repositories.entities.user import User
from prism.repositories.entities.audit import AuditLog
from prism.repositories.entities.incentive_rules_master import IncentiveRuleMaster
from prism.repositories.incentive_rules import incentive_rules_repository as repo
from prism.services.incentive_rules import incentive_rules_service as service
from prism.models.incentive_rules.schemas import IncentiveRuleBatchUpdateItem

class MasterAuditTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        for table in (User.__table__, IncentiveRuleMaster.__table__, AuditLog.__table__):
            table.create(self.engine)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def create_rule(self):
        return repo.create_rule(self.db, {
            "division": "ampcusTechClient", "rule_category": "FTE_LEADERSHIP",
            "role": "Manager", "amount": Decimal("1500"),
        })

    def test_all_mutations_record_before_after_and_delete(self):
        row = self.create_rule()
        rule_id = row.id
        repo.update_rule(self.db, rule_id, {"amount": Decimal("2500")})
        repo.toggle_active(self.db, rule_id)
        repo.soft_delete(self.db, rule_id)
        repo.hard_delete(self.db, rule_id)
        self.db.commit()
        logs = self.db.scalars(select(AuditLog).order_by(AuditLog.id)).all()
        self.assertEqual([log.metadata_json["operation"] for log in logs],
                         ["Created", "Updated", "Toggled", "Deactivated", "Deleted"])
        change = logs[1].metadata_json["changes"]["amount"]
        self.assertEqual(Decimal(str(change["before"])), Decimal("1500"))
        self.assertEqual(Decimal(str(change["after"])), Decimal("2500"))
        self.assertEqual(logs[-1].entity_id, str(rule_id))
        self.assertIsNone(logs[-1].metadata_json["after"])

    def test_rollback_removes_audit_and_rule_together(self):
        self.create_rule()
        self.db.rollback()
        self.assertEqual(self.db.scalars(select(AuditLog)).all(), [])
        self.assertEqual(self.db.scalars(select(IncentiveRuleMaster)).all(), [])

    def test_batch_update_is_audited(self):
        row = self.create_rule()
        self.db.commit()
        service.batch_update_rules(self.db, [IncentiveRuleBatchUpdateItem(
            id=row.id, data={"amount": 3000})])
        logs = self.db.scalars(select(AuditLog).order_by(AuditLog.id)).all()
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[-1].metadata_json["operation"], "Updated")

    def test_missing_rule_does_not_log(self):
        self.assertIsNone(repo.update_rule(self.db, 999, {"amount": 3000}))
        self.assertFalse(repo.hard_delete(self.db, 999))
        self.assertEqual(self.db.scalars(select(AuditLog)).all(), [])

if __name__ == "__main__":
    unittest.main()
