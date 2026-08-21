"""VLOOKUP cancel / draft / continue persistence."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.repositories.entities.audit import AuditAction, AuditLog
from app.repositories.entities.vlookup import VLookupUploadBatch
from app.services.vlookup.vlookup_service import (
    cancel_batch,
    continue_draft,
    discard_draft,
    get_draft,
    list_drafts,
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


def _user():
    return SimpleNamespace(id=None, email="accounts@example.com", full_name="Accounts")


def _running_batch(db, batch_id: str = "batch-draft-1") -> VLookupUploadBatch:
    row = VLookupUploadBatch(
        batch_id=batch_id,
        file_type="template_and_messy",
        filename="Candidate_Master.xlsx + messy.xlsx",
        status="running",
        stage="review",
        matched_count=10,
        unmatched_count=2,
        target_month="2026-08",
        uploaded_by="accounts@example.com",
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_cancel_saves_draft_without_deleting_batch(db):
    _running_batch(db)
    user = _user()
    draft = cancel_batch(db, "batch-draft-1", user)

    assert draft.status == "draft"
    assert draft.filename == "Candidate_Master.xlsx + messy.xlsx"
    assert draft.target_month == "2026-08"
    assert draft.uploaded_by == "accounts@example.com"
    assert draft.cancelled_by == "accounts@example.com"
    assert draft.resume_state["stage"] == "review"

    listed = list_drafts(db)
    assert len(listed.drafts) == 1
    assert listed.drafts[0].batch_id == "batch-draft-1"

    persisted = db.query(VLookupUploadBatch).filter_by(batch_id="batch-draft-1").one()
    assert persisted.status == "draft"
    assert persisted.matched_count == 10

    logs = db.query(AuditLog).all()
    assert any(row.action == AuditAction.VLOOKUP_MATCH_CANCELLED for row in logs)


def test_continue_draft_is_idempotent(db):
    _running_batch(db)
    user = _user()
    cancel_batch(db, "batch-draft-1", user)

    first = continue_draft(db, "batch-draft-1", user)
    second = continue_draft(db, "batch-draft-1", user)

    assert first.status == "running"
    assert second.status == "running"
    assert first.batch_id == second.batch_id == "batch-draft-1"
    assert db.query(VLookupUploadBatch).count() == 1

    with pytest.raises(Exception):
        get_draft(db, "batch-draft-1")

    resume_logs = [
        row for row in db.query(AuditLog).all() if row.action == AuditAction.VLOOKUP_DRAFT_RESUMED
    ]
    assert len(resume_logs) == 1


def test_discard_draft_deletes_only_that_batch(db):
    _running_batch(db, "keep-me")
    _running_batch(db, "drop-me")
    user = _user()
    cancel_batch(db, "drop-me", user)
    discard_draft(db, "drop-me", user)

    remaining = db.query(VLookupUploadBatch).all()
    assert [row.batch_id for row in remaining] == ["keep-me"]
