import base64


def _basic_auth_header(username: str, password: str) -> dict:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_no_password_gate_when_env_var_unset(client):
    # tests/conftest.py's client fixture never sets SITE_PASSWORD.
    response = client.get("/tasks")
    assert response.status_code == 200


def test_health_check_bypasses_password_gate(client, monkeypatch):
    monkeypatch.setenv("SITE_PASSWORD", "correct-horse")
    response = client.get("/health")
    assert response.status_code == 200


def test_protected_route_rejects_missing_credentials(client, monkeypatch):
    monkeypatch.setenv("SITE_PASSWORD", "correct-horse")
    response = client.get("/tasks")
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic")


def test_protected_route_rejects_wrong_password(client, monkeypatch):
    monkeypatch.setenv("SITE_PASSWORD", "correct-horse")
    response = client.get("/tasks", headers=_basic_auth_header("anyone", "wrong"))
    assert response.status_code == 401


def test_protected_route_accepts_correct_password(client, monkeypatch):
    monkeypatch.setenv("SITE_PASSWORD", "correct-horse")
    response = client.get("/tasks", headers=_basic_auth_header("anyone", "correct-horse"))
    assert response.status_code == 200


def test_username_is_not_checked(client, monkeypatch):
    # Single shared-secret model — any username is accepted as long as the
    # password matches, matching the design note in app/middleware.py.
    monkeypatch.setenv("SITE_PASSWORD", "correct-horse")
    response = client.get("/tasks", headers=_basic_auth_header("whoever", "correct-horse"))
    assert response.status_code == 200
