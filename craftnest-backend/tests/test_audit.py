import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.audit_log import AuditLog

@pytest.mark.asyncio
async def test_audit_logs_signup_and_login_scenarios(client: AsyncClient, db: AsyncSession):
    # Ensure audit logs table is empty initially
    initial_logs = (await db.execute(select(AuditLog))).scalars().all()
    assert len(initial_logs) == 0

    unique_suffix = uuid.uuid4().hex[:8]
    email = f"audit_test_{unique_suffix}@example.com"
    password = "SecurePassword123!"
    full_name = "Audit Test User"

    # Scenario 1: A successful signup creates exactly one audit_logs row with event_type='auth.signup'
    signup_resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": password, "full_name": full_name, "role": "buyer"}
    )
    assert signup_resp.status_code == 201
    signup_data = signup_resp.json()

    # Fetch logs from DB
    result_signup = await db.execute(select(AuditLog).order_by(AuditLog.created_at.asc()))
    logs_signup = result_signup.scalars().all()
    assert len(logs_signup) == 1
    assert logs_signup[0].event_type == "auth.signup"
    assert logs_signup[0].details is None
    assert str(logs_signup[0].user_id) == signup_data["user_id"]

    # Clear current session to read any fresh committed changes
    db.expire_all()

    # Scenario 2: A failed login creates a row with event_type='auth.login.failure' and details.reason set
    login_fail_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "wrong_password"}
    )
    assert login_fail_resp.status_code == 401

    # Fetch logs from DB
    db.expire_all()
    result_fail = await db.execute(select(AuditLog).order_by(AuditLog.created_at.asc()))
    logs_fail = result_fail.scalars().all()
    assert len(logs_fail) == 2
    # Second log should be the login failure
    assert logs_fail[1].event_type == "auth.login.failure"
    assert logs_fail[1].details is not None
    assert logs_fail[1].details["attempted_email"] == email.lower()
    assert logs_fail[1].details["reason"] == "wrong_password"

    # Scenario 3: A successful then failed login creates two rows (success + failure)
    # Let's perform a successful login first
    login_success_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password}
    )
    assert login_success_resp.status_code == 200

    # Let's perform a second failed login (non-existent email)
    login_fail2_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": f"no_such_user_{unique_suffix}@example.com", "password": password}
    )
    assert login_fail2_resp.status_code == 401

    # Verify audit logs in DB
    db.expire_all()
    result_all = await db.execute(select(AuditLog).order_by(AuditLog.created_at.asc()))
    logs_all = result_all.scalars().all()
    
    # We should have:
    # 1. auth.signup (signup)
    # 2. auth.login.failure (failed login - wrong password)
    # 3. auth.login.success (successful login)
    # 4. auth.login.failure (failed login - no such user)
    assert len(logs_all) == 4
    
    assert logs_all[2].event_type == "auth.login.success"
    assert str(logs_all[2].user_id) == signup_data["user_id"]
    
    assert logs_all[3].event_type == "auth.login.failure"
    assert logs_all[3].details["reason"] == "no_such_user"
    assert logs_all[3].details["attempted_email"] == f"no_such_user_{unique_suffix}@example.com"
