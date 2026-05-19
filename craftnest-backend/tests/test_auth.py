import pytest
import uuid
import time
import asyncio
from jose import jwt
from httpx import AsyncClient
from app.core.config import settings

@pytest.mark.asyncio
async def test_auth_flow_comprehensive(client: AsyncClient):
    unique_suffix = uuid.uuid4().hex[:8]
    email = f"test_{unique_suffix}@example.com"
    password = "SecurePassword123!"
    full_name = "Auth Test User"
    
    # 1. Signup with valid data returns 201 + tokens
    signup_resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": password, "full_name": full_name, "role": "buyer"}
    )
    assert signup_resp.status_code == 201
    signup_data = signup_resp.json()
    assert "access_token" in signup_data
    assert "refresh_token" in signup_data
    assert "user_id" in signup_data
    assert signup_data["role"] == "buyer"
    
    # 2. Signup with duplicate email returns 409
    dup_resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": password, "full_name": full_name, "role": "buyer"}
    )
    assert dup_resp.status_code == 409
    assert "already exists" in dup_resp.json()["detail"]
    
    # 3. Signup with short password returns 422
    short_resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": f"short_{unique_suffix}@example.com", "password": "123", "role": "buyer"}
    )
    assert short_resp.status_code == 422
    
    # 4. Login with wrong password returns 401
    login_wrong_pwd = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword123!"}
    )
    assert login_wrong_pwd.status_code == 401
    assert login_wrong_pwd.json()["detail"] == "Incorrect email or password"
    
    # 5. Login with non-existent email returns 401 (same shape as wrong password)
    login_non_existent = await client.post(
        "/api/v1/auth/login",
        json={"email": f"non_existent_{unique_suffix}@example.com", "password": password}
    )
    assert login_non_existent.status_code == 401
    assert login_non_existent.json() == login_wrong_pwd.json()  # matches same shape
    
    # 6. Happy path login
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password}
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    access_token = login_data["access_token"]
    refresh_token = login_data["refresh_token"]
    user_id = login_data["user_id"]
    
    # 7. GET /me with valid access token returns the user
    headers = {"Authorization": f"Bearer {access_token}"}
    me_resp = await client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == email.lower()
    assert me_data["full_name"] == full_name
    assert me_data["role"] == "buyer"
    assert me_data["is_active"] is True
    
    # 8. GET /me with no token returns 401
    me_no_token = await client.get("/api/v1/auth/me")
    assert me_no_token.status_code == 401
    
    # 9. GET /me with expired token returns 401
    expired_token = jwt.encode(
        {"sub": str(user_id), "role": "buyer", "exp": int(time.time()) - 3600},
        settings.JWT_SECRET,
        algorithm="HS256"
    )
    me_expired = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert me_expired.status_code == 401
    
    # 10. refresh returns a new access token
    await asyncio.sleep(1)  # Ensure JWT exp timestamp differs
    refresh_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert refresh_resp.status_code == 200
    refresh_data = refresh_resp.json()
    new_access_token = refresh_data["access_token"]
    new_refresh_token = refresh_data["refresh_token"]
    assert new_access_token != access_token
    assert new_refresh_token != refresh_token
    
    # 11. refresh with revoked token returns 401 (token rotation makes old token revoked)
    revoked_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert revoked_resp.status_code == 401
    assert "revoked" in revoked_resp.json()["detail"]
    
    # 12. Logout revokes the new refresh token
    logout_resp = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": new_refresh_token},
        headers={"Authorization": f"Bearer {new_access_token}"}
    )
    assert logout_resp.status_code == 200
    
    # Trying to refresh again with the logged-out token returns 401
    revoked_logout_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_refresh_token}
    )
    assert revoked_logout_resp.status_code == 401
