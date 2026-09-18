"""Pytest fixtures for API integration tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.main import app
from app.services.common.seed import seed_database

TEST_DB_URL = "sqlite://"


@pytest.fixture()
def client():
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    from app.repositories.auth import auth_repository
    from app.security.auth import hash_password

    db = TestingSessionLocal()
    try:
        seed_database(db)
        # Also seed ACCOUNTS and VIEWER users for testing RBAC
        role_accounts = auth_repository.get_role_by_name(db, "ACCOUNTS")
        if not role_accounts:
            role_accounts = auth_repository.create_role(db, name="ACCOUNTS", description="Accounts Operator")
        role_viewer = auth_repository.get_role_by_name(db, "VIEWER")
        if not role_viewer:
            role_viewer = auth_repository.create_role(db, name="VIEWER", description="Read-only Viewer")

        if not auth_repository.get_user_by_email(db, "accounts@example.com"):
            auth_repository.create_user(
                db,
                email="accounts@example.com",
                full_name="Accounts Operator",
                hashed_password=hash_password("Accounts@123"),
                roles=[role_accounts] if role_accounts else [],
                is_active=True,
            )
        if not auth_repository.get_user_by_email(db, "viewer@example.com"):
            auth_repository.create_user(
                db,
                email="viewer@example.com",
                full_name="Read-only Viewer",
                hashed_password=hash_password("Viewer@123"),
                roles=[role_viewer] if role_viewer else [],
                is_active=True,
            )
        db.commit()
    finally:
        db.close()

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "Admin@123"},
    )
    assert response.status_code == 200, response.text
    token = response.cookies.get("access_token")
    assert token is not None, "Login did not set access_token cookie"
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def accounts_headers(client: TestClient) -> dict[str, str]:
    """Provide auth headers for an ACCOUNTS-only user."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "accounts@example.com", "password": "Accounts@123"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def viewer_headers(client: TestClient) -> dict[str, str]:
    """Provide auth headers for a VIEWER-only user."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "viewer@example.com", "password": "Viewer@123"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


