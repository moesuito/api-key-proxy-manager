from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["default_model"] == "z-ai/glm-5.2"
    assert data["proxy_api_key_configured"] is True
    assert "key_manager" in data


def test_v1_models_endpoint():
    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert len(data["data"]) >= 1
    assert data["data"][0]["id"] == "z-ai/glm-5.2"


def test_unauthorized_access():
    """Tests if proxy blocks unauthenticated requests with HTTP 401."""
    res_openai = client.post("/v1/chat/completions", json={"messages": []})
    assert res_openai.status_code == 401
    assert "Proxy" in res_openai.json()["error"]["message"]

    res_anthropic = client.post("/v1/messages", json={"messages": []})
    assert res_anthropic.status_code == 401
    assert "Proxy" in res_anthropic.json()["error"]["message"]


def test_authorized_access_header():
    """Tests if valid authorization header passes proxy authentication."""
    headers = {"Authorization": f"Bearer {settings.PROXY_API_KEY}"}
    res = client.post("/v1/chat/completions", json={"messages": []}, headers=headers)
    assert res.status_code != 401 or "Invalid or missing Proxy API Key" not in res.json().get("error", {}).get("message", "")
