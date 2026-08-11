def test_login_returns_jwt(client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "Admin@123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_me_requires_auth(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_me_with_token(client, auth_headers):
    resp = client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "admin@example.com"
