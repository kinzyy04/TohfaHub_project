"""
Tests for security hardening changes:

1. Security response headers present on every response.
2. Request body size limit (1 MB) returns 413 when Content-Length > 1 048 576.
3. POST /auth/login returns 429 after 5 attempts within the rate limit window.
"""

import pytest
from httpx import AsyncClient
from app.core.rate_limit import limiter


# ---------------------------------------------------------------------------
# Test 1 — Security headers
# ---------------------------------------------------------------------------

EXPECTED_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
}

@pytest.mark.asyncio
async def test_security_headers_present_on_public_endpoint(client: AsyncClient):
    """Every response must carry the security hardening headers."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200

    for header, value in EXPECTED_HEADERS.items():
        assert header in response.headers, f"Missing header: {header}"
        assert response.headers[header] == value, (
            f"Header {header} mismatch: expected {value!r}, got {response.headers[header]!r}"
        )


@pytest.mark.asyncio
async def test_csp_header_present(client: AsyncClient):
    """Content-Security-Policy must be present and contain 'self'."""
    response = await client.get("/api/v1/health")
    assert "Content-Security-Policy" in response.headers
    csp = response.headers["Content-Security-Policy"]
    assert "'self'" in csp
    assert "default-src" in csp


@pytest.mark.asyncio
async def test_security_headers_on_api_endpoint(client: AsyncClient):
    """Security headers must appear on API data endpoints too, not just health."""
    response = await client.get("/api/v1/browse/categories")
    # categories returns 200 (empty list) in a fresh test db
    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"


# ---------------------------------------------------------------------------
# Test 2 — Request body size limit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_body_size_limit_json_413(client: AsyncClient):
    """
    A JSON POST with Content-Length > 1 048 576 bytes must receive 413,
    enforced by our body_size_limit_middleware before the request is processed.
    """
    oversized_body = b'{"data": "' + b"x" * 1_100_000 + b'"}'
    response = await client.post(
        "/api/v1/auth/login",
        content=oversized_body,
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(oversized_body)),
        },
    )
    assert response.status_code == 413
    assert "1 MB" in response.json()["detail"] or "limit" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_body_size_limit_allows_normal_json(client: AsyncClient):
    """
    A small JSON payload well under 1 MB must NOT be rejected by the middleware
    (it may still return 401 for bad credentials, but not 413).
    """
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "wrongpass"},
    )
    # 401 = credentials were wrong; 413 would mean size limit incorrectly fired
    assert response.status_code != 413


# ---------------------------------------------------------------------------
# Test 3 — Login rate-limit (5/minute → 6th call = 429)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_rate_limit_429_on_6th_attempt(client: AsyncClient):
    """
    POST /auth/login is limited to 5/minute per IP.
    The first 5 calls must return 401 (bad credentials).
    The 6th call must return 429 Too Many Requests.
    """
    limiter.reset()

    url = "/api/v1/auth/login"
    payload = {"email": "brute_force_test@example.com", "password": "WrongPass!"}

    try:
        for i in range(5):
            resp = await client.post(url, json=payload)
            assert resp.status_code == 401, (
                f"Expected 401 on attempt {i+1}, got {resp.status_code}"
            )

        resp_429 = await client.post(url, json=payload)
        assert resp_429.status_code == 429
        data = resp_429.json()
        assert "Too many requests" in data["detail"]
        assert "Retry-After" in resp_429.headers
        assert int(resp_429.headers["Retry-After"]) > 0
    finally:
        limiter.reset()
