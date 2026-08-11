import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_DB = Path(__file__).resolve().parent / "test_incentive.db"
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["SEED_ON_STARTUP"] = "false"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["ENVIRONMENT"] = "test"

from app.core.config import get_settings

get_settings.cache_clear()

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    from app.db.init_db import init_db

    db = SessionLocal()
    try:
        init_db(db)
    finally:
        db.close()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_headers(client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "Admin@123"},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
