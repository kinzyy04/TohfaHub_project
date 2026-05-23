import pytest
from httpx import AsyncClient
from sqlalchemy.future import select
from app.models.audit_log import AuditLog
from app.services.admin_service import clear_stats_cache
from app.models.user import User

@pytest.mark.asyncio
async def test_admin_stats_buyer_403(client: AsyncClient, buyer_token: str):
    response = await client.get(
        "/api/v1/admin/stats",
        headers={"Authorization": f"Bearer {buyer_token}"}
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required."

@pytest.mark.asyncio
async def test_admin_stats_seller_403(client: AsyncClient, seller_token: str):
    response = await client.get(
        "/api/v1/admin/stats",
        headers={"Authorization": f"Bearer {seller_token}"}
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required."

@pytest.mark.asyncio
async def test_admin_stats_no_token_401(client: AsyncClient):
    response = await client.get("/api/v1/admin/stats")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_admin_stats_details(client: AsyncClient, admin_token: str, db_session):
    # Clear the cache first to start fresh
    clear_stats_cache()

    response = await client.get(
        "/api/v1/admin/stats",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()

    # Verify dictionary keys and nested structure
    assert "users" in data
    assert "products" in data
    assert "orders" in data
    assert "gmv_paise" in data
    assert "top_sellers" in data
    assert "daily_new_users_7d" in data

    assert "total" in data["users"]
    assert "new_today" in data["users"]
    assert "buyers" in data["users"]
    assert "sellers" in data["users"]

    assert "total" in data["products"]
    assert "active" in data["products"]

    assert "total" in data["orders"]
    assert "pending" in data["orders"]
    assert "processing" in data["orders"]
    assert "shipped" in data["orders"]
    assert "delivered" in data["orders"]

    assert isinstance(data["gmv_paise"], int)
    assert isinstance(data["top_sellers"], list)
    assert isinstance(data["daily_new_users_7d"], list)
    assert len(data["daily_new_users_7d"]) == 7

    # Verify audit log entry
    audit_res = await db_session.execute(
        select(AuditLog).where(AuditLog.event_type == "admin.stats.viewed")
    )
    audit = audit_res.scalar_one_or_none()
    assert audit is not None

    # Test cache behavior (second call without clearing cache uses cached results)
    # Let's create a new user manually
    new_user = User(email="cache_test@example.com", password_hash="hash", role="buyer")
    db_session.add(new_user)
    await db_session.flush()

    # Call /stats without clearing cache -> users.total should be the same as before
    response_cached = await client.get(
        "/api/v1/admin/stats",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response_cached.status_code == 200
    assert response_cached.json()["users"]["total"] == data["users"]["total"]

    # Now clear the cache and call /stats -> users.total should increase by 1, and new_today should increase by 1
    clear_stats_cache()
    response_updated = await client.get(
        "/api/v1/admin/stats",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response_updated.status_code == 200
    assert response_updated.json()["users"]["total"] == data["users"]["total"] + 1
    assert response_updated.json()["users"]["new_today"] == data["users"]["new_today"] + 1
