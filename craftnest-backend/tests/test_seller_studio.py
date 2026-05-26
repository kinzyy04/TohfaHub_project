import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
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

async def setup_seller(client: AsyncClient, db: AsyncSession, email: str) -> tuple[User, dict]:
    user = await create_user_direct(db, email, "buyer")
    headers = get_auth_headers(user.id, "buyer")
    
    # Become a seller via onboarding
    payload = {
        "store_name": f"Store {uuid.uuid4().hex[:8]}",
        "store_handle": f"store-{uuid.uuid4().hex[:8]}",
        "bio": "Init bio"
    }
    resp = await client.post("/api/v1/seller/become-a-seller", json=payload, headers=headers)
    assert resp.status_code == 201
    
    headers = get_auth_headers(user.id, "seller")
    return user, headers

@pytest.mark.asyncio
async def test_seller_studio_flow(client: AsyncClient, db: AsyncSession):
    # Setup seller
    user, headers = await setup_seller(client, db, "studio_test@example.com")
    
    # (a) GET /seller/profile -> 200, correct fields present
    resp_get = await client.get("/api/v1/seller/profile", headers=headers)
    assert resp_get.status_code == 200
    data_get = resp_get.json()
    assert "store_name" in data_get
    assert "store_handle" in data_get
    assert "bio" in data_get
    assert "location" in data_get
    assert "website_url" in data_get
    assert "artisan_story" in data_get
    assert "avatar_url" in data_get
    assert "is_accepting_orders" in data_get
    assert "is_online" in data_get
    assert "created_at" in data_get
    
    # (b) PATCH /seller/profile with bio update -> 200, bio changed
    payload_patch = {
        "bio": "Updated bio details",
        "location": "New York, USA",
        "website_url": "https://example.com/store"
    }
    resp_patch = await client.patch("/api/v1/seller/profile", json=payload_patch, headers=headers)
    assert resp_patch.status_code == 200
    data_patch = resp_patch.json()
    assert data_patch["bio"] == "Updated bio details"
    assert data_patch["location"] == "New York, USA"
    assert data_patch["website_url"] == "https://example.com/store"
    
    # (c) PATCH /seller/profile with store_handle -> 422
    payload_invalid = {
        "store_handle": "attempt-to-change-handle"
    }
    resp_invalid = await client.patch("/api/v1/seller/profile", json=payload_invalid, headers=headers)
    assert resp_invalid.status_code == 422
    assert "Store handle cannot be changed after creation." in resp_invalid.json()["detail"]

    # Test extra forbidden field in PATCH /seller/profile -> 422
    payload_extra = {
        "unknown_field": "some_value"
    }
    resp_extra = await client.patch("/api/v1/seller/profile", json=payload_extra, headers=headers)
    assert resp_extra.status_code == 422
    
    # (d) POST /toggle-orders twice -> flips and flips back correctly
    assert data_get["is_accepting_orders"] is True
    
    # Flip 1 (True -> False)
    resp_toggle1 = await client.post("/api/v1/seller/profile/toggle-orders", headers=headers)
    assert resp_toggle1.status_code == 200
    data_toggle1 = resp_toggle1.json()
    assert data_toggle1["is_accepting_orders"] is False
    assert data_toggle1["message"] == "Your store is paused. Buyers cannot place orders."
    
    # Flip 2 (False -> True)
    resp_toggle2 = await client.post("/api/v1/seller/profile/toggle-orders", headers=headers)
    assert resp_toggle2.status_code == 200
    data_toggle2 = resp_toggle2.json()
    assert data_toggle2["is_accepting_orders"] is True
    assert data_toggle2["message"] == "Your store is now open ✦"

    # (e) PATCH /payout-details with invalid payout_method -> 422
    payload_payout_invalid = {
        "payout_method": "invalid_method",
        "masked_account": "1234"
    }
    resp_payout_invalid = await client.patch("/api/v1/seller/payout-details", json=payload_payout_invalid, headers=headers)
    assert resp_payout_invalid.status_code == 422
    
    # PATCH /payout-details with valid payout_method -> 200
    payload_payout_valid = {
        "payout_method": "UPI",
        "masked_account": "UPI_ID_123"
    }
    resp_payout_valid = await client.patch("/api/v1/seller/payout-details", json=payload_payout_valid, headers=headers)
    assert resp_payout_valid.status_code == 200
    data_payout = resp_payout_valid.json()
    assert data_payout["payout_method"] == "UPI"
    assert data_payout["masked_account"] == "UPI_ID_123"
    assert "pending_payout_amount" in data_payout
    assert "payout_schedule" in data_payout

    # Test extra forbidden field in PATCH /payout-details -> 422
    payload_payout_extra = {
        "payout_method": "UPI",
        "extra_field": "val"
    }
    resp_payout_extra = await client.patch("/api/v1/seller/payout-details", json=payload_payout_extra, headers=headers)
    assert resp_payout_extra.status_code == 422

    # (f) All endpoints without auth -> 401
    resp_get_no_auth = await client.get("/api/v1/seller/profile")
    assert resp_get_no_auth.status_code == 401

    resp_patch_no_auth = await client.patch("/api/v1/seller/profile", json={"bio": "no auth"})
    assert resp_patch_no_auth.status_code == 401

    resp_toggle_no_auth = await client.post("/api/v1/seller/profile/toggle-orders")
    assert resp_toggle_no_auth.status_code == 401

    resp_payout_no_auth = await client.patch("/api/v1/seller/payout-details", json={"payout_method": "UPI"})
    assert resp_payout_no_auth.status_code == 401

    # Non-seller user access -> 404
    non_seller = await create_user_direct(db, "non_seller@example.com", "buyer")
    non_seller_headers = get_auth_headers(non_seller.id, "buyer")
    
    resp_get_non_seller = await client.get("/api/v1/seller/profile", headers=non_seller_headers)
    assert resp_get_non_seller.status_code == 404
    
    resp_patch_non_seller = await client.patch("/api/v1/seller/profile", json={"bio": "test"}, headers=non_seller_headers)
    assert resp_patch_non_seller.status_code == 404
    
    resp_toggle_non_seller = await client.post("/api/v1/seller/profile/toggle-orders", headers=non_seller_headers)
    assert resp_toggle_non_seller.status_code == 404

    resp_payout_non_seller = await client.patch("/api/v1/seller/payout-details", json={"payout_method": "UPI"}, headers=non_seller_headers)
    assert resp_payout_non_seller.status_code == 404
