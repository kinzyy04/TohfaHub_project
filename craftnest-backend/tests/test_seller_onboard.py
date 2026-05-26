import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.user import User
from app.models.seller import SellerProfile, SellerOnboardingStatus, SellerPayoutDetails
from app.core.security import create_access_token

def get_auth_headers(user_id: uuid.UUID, role: str) -> dict:
    token = create_access_token(user_id, role)
    return {"Authorization": f"Bearer {token}"}

async def create_user_direct(db: AsyncSession, email: str, role: str) -> User:
    user = User(
        email=email,
        password_hash="fake_hash",
        full_name="Test User",
        role=role,
        is_active=True
    )
    db.add(user)
    await db.flush()
    return user

@pytest.mark.asyncio
async def test_seller_onboarding_flow(client: AsyncClient, db: AsyncSession):
    # Create a user (initially a buyer)
    user = await create_user_direct(db, "onboard_test@example.com", "buyer")
    headers = get_auth_headers(user.id, "buyer")

    # (c) GET /studio/shell before onboarding -> 404
    resp_shell_before = await client.get("/api/v1/seller/studio/shell", headers=headers)
    assert resp_shell_before.status_code == 404
    assert resp_shell_before.json()["detail"] == "No seller profile found. Complete onboarding first."

    # (a) POST /become-a-seller with valid data -> 201, seller_id in response
    payload = {
        "store_name": "My Handcrafted Store",
        "store_handle": "my-handcrafted-store",
        "bio": "Beautiful handmade goods."
    }
    resp_become = await client.post("/api/v1/seller/become-a-seller", json=payload, headers=headers)
    assert resp_become.status_code == 201
    data_become = resp_become.json()
    assert "seller_id" in data_become
    assert data_become["store_name"] == "My Handcrafted Store"
    assert data_become["store_handle"] == "my-handcrafted-store"
    assert len(data_become["onboarding_steps"]) == 8
    for step in data_become["onboarding_steps"]:
        assert step["is_complete"] is False

    # (b) POST again with same store_handle -> 409
    user2 = await create_user_direct(db, "onboard_test2@example.com", "buyer")
    headers2 = get_auth_headers(user2.id, "buyer")
    payload2 = {
        "store_name": "Different Name",
        "store_handle": "my-handcrafted-store",
        "bio": "Conflict store."
    }
    resp_conflict = await client.post("/api/v1/seller/become-a-seller", json=payload2, headers=headers2)
    assert resp_conflict.status_code == 409

    # (d) GET /studio/shell after onboarding -> 200 with correct shape
    resp_shell_after = await client.get("/api/v1/seller/studio/shell", headers=headers)
    assert resp_shell_after.status_code == 200
    data_shell = resp_shell_after.json()
    assert data_shell["store_name"] == "My Handcrafted Store"
    assert data_shell["store_handle"] == "my-handcrafted-store"
    assert data_shell["is_accepting_orders"] is True
    assert data_shell["pending_payout_amount"] == 0.0
    assert data_shell["payout_schedule"] == "Every Monday 10 AM"
    assert data_shell["onboarding_progress"] == {"complete": 0, "total": 8}

    # (e) PATCH /onboarding/step/store_details -> 200, is_complete True
    resp_patch = await client.patch("/api/v1/seller/onboarding/step/store_details", headers=headers)
    assert resp_patch.status_code == 200
    data_patch = resp_patch.json()
    store_details_step = next(step for step in data_patch if step["step_key"] == "store_details")
    assert store_details_step["is_complete"] is True

    # (f) PATCH /onboarding/step/invalid_key -> 422
    resp_patch_invalid = await client.patch("/api/v1/seller/onboarding/step/invalid_step_key", headers=headers)
    assert resp_patch_invalid.status_code == 422
    assert "Invalid step key" in resp_patch_invalid.json()["detail"]
