import pytest
from httpx import AsyncClient
from app.core.rate_limit import limiter

@pytest.mark.asyncio
async def test_rate_limiting_login_endpoint(client: AsyncClient):
    # Ensure limiter starts with a clean slate
    limiter.reset()
    
    url = "/api/v1/auth/login"
    login_payload = {
        "email": "rate_limit_test@example.com",
        "password": "WrongPassword123!"
    }
    
    # 1. First 5 requests should return 401 Unauthorized (credentials check)
    for i in range(5):
        resp = await client.post(url, json=login_payload)
        assert resp.status_code == 401, f"Expected 401 on attempt {i+1}, got {resp.status_code}"
        
    # 2. The 6th request should hit the 5/minute limit and return 429 Too Many Requests
    resp_limit = await client.post(url, json=login_payload)
    
    try:
        assert resp_limit.status_code == 429
        
        # 3. Assert custom 429 error structure and Retry-After header
        data = resp_limit.json()
        assert "Too many requests" in data["detail"]
        assert "Retry-After" in resp_limit.headers
        assert int(resp_limit.headers["Retry-After"]) > 0
    finally:
        # Reset limiter state to not affect other tests
        limiter.reset()
