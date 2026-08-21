"""VLOOKUP month-scoped export: matched/accepted vs unmatched, no other-month dupes."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.repositories.entities.vlookup import (
    VLookupMatchedRecord,
    VLookupTemplateCandidate,
    VLookupUploadBatch,
)
from app.services.vlookup.vlookup_service import (
    _dedupe_export_rows,
    _hours_export_rows,
    _match_belongs_to_month,
    _matched_hours_export_rows,
)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _batch(db, batch_id: str = "batch-1") -> VLookupUploadBatch:
    row = VLookupUploadBatch(
        batch_id=batch_id,
        file_type="template_and_messy",
        filename="template.xlsx + messy.xlsx",
        status="completed",
        matched_count=2,
        unmatched_count=1,
        target_month="2025-06",
        uploaded_by="test",
        completed_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def _template(db, *, batch_id: str, cid: str, name: str, client: str, month: str) -> VLookupTemplateCandidate:
    row = VLookupTemplateCandidate(
        candidate_id=cid,
        candidate_name=name,
        client_name=client,
        template_hours=0,
        month=month,
        upload_batch_id=batch_id,
    )
    db.add(row)
    db.flush()
    return row


def _match(
    db,
    *,
    batch_id: str,
    template: VLookupTemplateCandidate | None,
    status: str,
    month: str,
    hours: int,
    name: str = "Ada Lopez",
    confidence: float = 0.99,
) -> VLookupMatchedRecord:
    row = VLookupMatchedRecord(
        template_candidate_id=template.id if template else None,
        template_candidate_name=template.candidate_name if template else name,
        template_candidate_id_str=template.candidate_id if template else None,
        messy_name_original=name,
        messy_client_name=template.client_name if template else "Acme",
        messy_month=month,
        weekly_breakdown={},
        total_hours=hours,
        confidence_score=confidence,
        match_status=status,
        match_method="test",
        match_explanation={"monthly_hours": {month: hours}, "hours_note": ""},
        upload_batch_id=batch_id,
        manually_reviewed=status == "accepted",
    )
    db.add(row)
    db.flush()
    return row


class TestDedupeAndMonthGate:
    def test_dedupe_prefers_accepted(self):
        rows = [
            {
                "Candidate ID": "C1",
                "Candidate Name": "Ada",
                "Client Name": "Acme",
                "Month": "2025-06",
                "Match Status": "matched",
                "Confidence": 0.99,
            },
            {
                "Candidate ID": "C1",
                "Candidate Name": "Ada",
                "Client Name": "Acme",
                "Month": "2025-06",
                "Match Status": "accepted",
                "Confidence": 0.80,
            },
        ]
        out = _dedupe_export_rows(rows)
        assert len(out) == 1
        assert out[0]["Match Status"] == "accepted"

    def test_month_gate_uses_template_or_messy_month(self):
        class T:
            month = "2025-06"

        class M:
            messy_month = "2025-07"

        assert _match_belongs_to_month(M(), T(), "2025-06") is True
        assert _match_belongs_to_month(M(), T(), "2025-08") is False


class TestMonthScopedExport:
    def test_matched_export_keeps_selected_month_only(self, db):
        _batch(db)
        june = _template(db, batch_id="batch-1", cid="C1", name="Ada Lopez", client="Acme", month="2025-06")
        july = _template(db, batch_id="batch-1", cid="C1", name="Ada Lopez", client="Acme", month="2025-07")
        august = _template(db, batch_id="batch-1", cid="C1", name="Ada Lopez", client="Acme", month="2025-08")
        _match(db, batch_id="batch-1", template=june, status="matched", month="2025-06", hours=40)
        _match(db, batch_id="batch-1", template=july, status="matched", month="2025-07", hours=32)
        _match(db, batch_id="batch-1", template=august, status="accepted", month="2025-08", hours=16)
        db.commit()

        _latest, june_rows = _matched_hours_export_rows(db, batch_id="batch-1", month_key="2025-06")
        assert len(june_rows) == 1
        assert june_rows[0]["Month"] == "2025-06"
        assert june_rows[0]["Hours Worked"] == 40
        assert june_rows[0]["Match Status"] == "matched"

        _latest, july_rows = _matched_hours_export_rows(db, batch_id="batch-1", month_key="2025-07")
        assert len(july_rows) == 1
        assert july_rows[0]["Hours Worked"] == 32

        _latest, aug_rows = _matched_hours_export_rows(db, batch_id="batch-1", month_key="2025-08")
        assert len(aug_rows) == 1
        assert aug_rows[0]["Match Status"] == "accepted"
        assert aug_rows[0]["Hours Worked"] == 16

    def test_unmatched_export_is_month_filtered_and_not_in_matched_file(self, db):
        _batch(db)
        matched = _template(db, batch_id="batch-1", cid="C1", name="Ada Lopez", client="Acme", month="2025-06")
        unmatched = _template(db, batch_id="batch-1", cid="C2", name="Pat Kim", client="Acme", month="2025-06")
        later_unmatched = _template(db, batch_id="batch-1", cid="C3", name="Sam Lee", client="Acme", month="2025-07")
        _match(db, batch_id="batch-1", template=matched, status="matched", month="2025-06", hours=40)
        _match(db, batch_id="batch-1", template=unmatched, status="unmatched", month="2025-06", hours=0, name="Pat Kim")
        _match(db, batch_id="batch-1", template=later_unmatched, status="unmatched", month="2025-07", hours=0, name="Sam Lee")
        db.commit()

        _latest, matched_rows = _matched_hours_export_rows(db, batch_id="batch-1", month_key="2025-06")
        assert [r["Candidate ID"] for r in matched_rows] == ["C1"]

        _latest, unmatched_rows, month = _hours_export_rows(
            db,
            batch_id="batch-1",
            statuses=["unmatched"],
            month_key="2025-06",
            require_template=False,
        )
        assert month == "2025-06"
        assert [r["Candidate ID"] for r in unmatched_rows] == ["C2"]
        assert unmatched_rows[0]["Match Status"] == "unmatched"

    def test_duplicate_same_month_rows_collapse_to_one(self, db):
        _batch(db)
        t1 = _template(db, batch_id="batch-1", cid="C1", name="Ada Lopez", client="Acme", month="2025-06")
        t2 = _template(db, batch_id="batch-1", cid="C1", name="Ada Lopez", client="Acme", month="2025-06")
        _match(db, batch_id="batch-1", template=t1, status="matched", month="2025-06", hours=40, confidence=0.80)
        _match(db, batch_id="batch-1", template=t2, status="accepted", month="2025-06", hours=40, confidence=0.70)
        db.commit()

        _latest, rows = _matched_hours_export_rows(db, batch_id="batch-1", month_key="2025-06")
        assert len(rows) == 1
        assert rows[0]["Match Status"] == "accepted"
