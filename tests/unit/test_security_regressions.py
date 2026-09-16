def test_protected_routes_require_auth(client):
    response = client.get("/api/v1/candidates")
    assert response.status_code == 401, response.text
