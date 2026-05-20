import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.future import select
from app.models.category import Category
from app.models.product import Product
from app.models.wishlist import Wishlist
from app.models.audit_log import AuditLog
from tests.conftest import create_user_token_helper

@pytest.fixture
async def category_id(db) -> uuid.UUID:
    cat = Category(
        slug="test-ceramics",
        display_name="Test Ceramics",
        description="A category for testing wishlists",
        icon_emoji="🏺"
    )
    db.add(cat)
    await db.flush()
    return cat.id

@pytest.fixture
async def seller_headers(seller_token: str) -> dict:
    return {"Authorization": f"Bearer {seller_token}"}

@pytest.fixture
async def buyer_headers(buyer_token: str) -> dict:
    return {"Authorization": f"Bearer {buyer_token}"}

@pytest.fixture
async def sample_product(client: AsyncClient, seller_headers: dict, category_id: uuid.UUID) -> dict:
    payload = {
        "title": "Glazed Clay Mug",
        "description": "Handcrafted clay mug",
        "price_paise": 1500,
        "stock": 5,
        "category_id": str(category_id),
        "image_urls": ["https://example.com/mug.jpg"]
    }
    res = await client.post("/api/v1/products", json=payload, headers=seller_headers)
    assert res.status_code == 201
    return res.json()

# ==========================================
# Wishlist Endpoints Tests
# ==========================================

@pytest.mark.asyncio
async def test_add_to_wishlist_success(
    client: AsyncClient,
    buyer_headers: dict,
    sample_product: dict,
    db,
):
    prod_id = sample_product["id"]
    response = await client.post(f"/api/v1/wishlist/{prod_id}", headers=buyer_headers)
    assert response.status_code == 200
    assert response.json()["message"] == "Product added to wishlist"

    # Verify audit log entry
    audit_res = await db.execute(
        select(AuditLog).where(AuditLog.event_type == "wishlist.added")
    )
    audit_log = audit_res.scalar_one_or_none()
    assert audit_log is not None
    assert audit_log.details.get("product_id") == prod_id

@pytest.mark.asyncio
async def test_add_to_wishlist_duplicate_idempotent(
    client: AsyncClient,
    buyer_headers: dict,
    sample_product: dict,
    db,
):
    prod_id = sample_product["id"]
    # First addition
    res1 = await client.post(f"/api/v1/wishlist/{prod_id}", headers=buyer_headers)
    assert res1.status_code == 200

    # Second addition should be idempotent and not error
    res2 = await client.post(f"/api/v1/wishlist/{prod_id}", headers=buyer_headers)
    assert res2.status_code == 200

    # Verify only one row exists in DB
    wishlist_res = await db.execute(
        select(Wishlist).where(Wishlist.product_id == uuid.UUID(prod_id))
    )
    wishlist_items = wishlist_res.scalars().all()
    assert len(wishlist_items) == 1

@pytest.mark.asyncio
async def test_add_to_wishlist_non_existent(client: AsyncClient, buyer_headers: dict):
    fake_id = str(uuid.uuid4())
    response = await client.post(f"/api/v1/wishlist/{fake_id}", headers=buyer_headers)
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_add_to_wishlist_unauthorized(client: AsyncClient, sample_product: dict):
    prod_id = sample_product["id"]
    response = await client.post(f"/api/v1/wishlist/{prod_id}")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_add_to_wishlist_seller_forbidden(
    client: AsyncClient,
    seller_headers: dict,
    sample_product: dict,
):
    prod_id = sample_product["id"]
    response = await client.post(f"/api/v1/wishlist/{prod_id}", headers=seller_headers)
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_get_wishlist_success(
    client: AsyncClient,
    buyer_headers: dict,
    sample_product: dict,
):
    prod_id = sample_product["id"]
    # Add to wishlist
    await client.post(f"/api/v1/wishlist/{prod_id}", headers=buyer_headers)

    # Fetch wishlist
    response = await client.get("/api/v1/wishlist", headers=buyer_headers)
    assert response.status_code == 200
    wishlist = response.json()
    assert len(wishlist) == 1
    assert wishlist[0]["id"] == prod_id
    assert wishlist[0]["title"] == "Glazed Clay Mug"
    assert wishlist[0]["price_paise"] == 1500
    assert wishlist[0]["image_urls"] == ["https://example.com/mug.jpg"]
    assert wishlist[0]["category_slug"] == "test-ceramics"

@pytest.mark.asyncio
async def test_remove_from_wishlist_success(
    client: AsyncClient,
    buyer_headers: dict,
    sample_product: dict,
    db,
):
    prod_id = sample_product["id"]
    # Add to wishlist
    await client.post(f"/api/v1/wishlist/{prod_id}", headers=buyer_headers)

    # Remove from wishlist
    response = await client.delete(f"/api/v1/wishlist/{prod_id}", headers=buyer_headers)
    assert response.status_code == 200
    assert response.json()["message"] == "Product removed from wishlist"

    # Verify audit log entry
    audit_res = await db.execute(
        select(AuditLog).where(AuditLog.event_type == "wishlist.removed")
    )
    audit_log = audit_res.scalar_one_or_none()
    assert audit_log is not None
    assert audit_log.details.get("product_id") == prod_id

    # Verify not in wishlist anymore
    res = await client.get("/api/v1/wishlist", headers=buyer_headers)
    assert len(res.json()) == 0

@pytest.mark.asyncio
async def test_remove_from_wishlist_not_found(
    client: AsyncClient,
    buyer_headers: dict,
    sample_product: dict,
):
    prod_id = sample_product["id"]
    # Not wishlisted yet
    response = await client.delete(f"/api/v1/wishlist/{prod_id}", headers=buyer_headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Product not in wishlist"
