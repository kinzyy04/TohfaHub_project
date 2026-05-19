from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings

client = TestClient(app)

def test_cors_preflight():
    # Test with one of the allowed origins
    origin = settings.CORS_ORIGINS[0]
    headers = {
        "Origin": origin,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Authorization"
    }
    
    # We can send an OPTIONS request to any endpoint, e.g., /health
    response = client.options("/health", headers=headers)
    
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin
    assert "GET" in response.headers.get("access-control-allow-methods", "")
    assert "Authorization" in response.headers.get("access-control-allow-headers", "")
    assert response.headers.get("access-control-allow-credentials") == "true"
    assert response.headers.get("access-control-max-age") == "600"

def test_cors_disallowed_origin():
    # Test with a disallowed origin to ensure wildcard is not used
    origin = "https://evil.com"
    headers = {
        "Origin": origin,
        "Access-Control-Request-Method": "GET",
    }
    
    response = client.options("/health", headers=headers)
    
    # Should either reject the request or not include the disallowed origin
    assert response.headers.get("access-control-allow-origin") != origin
