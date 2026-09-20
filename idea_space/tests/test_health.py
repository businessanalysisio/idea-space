from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_static_css_is_served():
    response = client.get("/static/app.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
