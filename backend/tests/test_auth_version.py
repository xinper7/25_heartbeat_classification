import jwt
from app.config import get_settings


def test_password_change_revokes_previous_sessions_and_legacy_tokens(client, headers):
    old = headers("analyst")
    payload = jwt.decode(old["Authorization"].split()[1], get_settings().jwt_secret, algorithms=["HS256"])
    payload.pop("ver")
    legacy = {"Authorization": "Bearer " + jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")}
    assert client.get("/api/v1/auth/me", headers=legacy).status_code == 200
    invalid = client.post("/api/v1/auth/password", headers=old,
                          json={"current_password": "wrong", "new_password": "a-new-password-123!"})
    assert invalid.status_code == 400
    assert client.get("/api/v1/auth/me", headers=old).status_code == 200
    response = client.post("/api/v1/auth/password", headers=old,
                           json={"current_password": "test-password-123!", "new_password": "a-new-password-123!"})
    assert response.status_code == 200
    for session in (old, legacy):
        assert client.get("/api/v1/auth/me", headers=session).status_code == 401
    assert client.get("/api/v1/auth/me", headers=headers("reviewer")).status_code == 200
    assert client.post("/api/v1/auth/login", json={"username": "analyst", "password": "test-password-123!"}).status_code == 401
    login = client.post("/api/v1/auth/login", json={"username": "analyst", "password": "a-new-password-123!"})
    assert login.status_code == 200
    new = {"Authorization": "Bearer " + login.json()["result"]["access_token"]}
    assert client.get("/api/v1/auth/me", headers=new).status_code == 200


def test_health_exposes_the_loaded_backend_revision(client):
    from app.version import REVISION, STARTED_AT
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    result = health.json()["result"]
    assert result["revision"] == REVISION
    assert result["started_at"] == STARTED_AT
