import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.future import select
from app.models.category import Category
from app.models.product import Product
from app.models.audit_log import AuditLog

@pytest.fixture
async def category_id(db) -> uuid.UUID:
    cat = Category(
        slug="test-candles",
        display_name="Test Candles",
        description="A category for testing products",
        icon_emoji="🕯️"
    )
    db.add(cat)
    await db.flush()
    return cat.id

@pytest.fixture
async def other_category_id(db) -> uuid.UUID:
    cat = Category(
        slug="test-soaps",
        display_name="Test Soaps",
        description="Another category for testing",
        icon_emoji="🧼"
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

# ==========================================
# POST /api/v1/products (Create Endpoint)
# ==========================================

@pytest.mark.asyncio
async def test_create_product_success(client: AsyncClient, seller_headers: dict, category_id: uuid.UUID, db):
    payload = {
        "title": "Scented Candle",
        "description": "A lavender scented candle",
        "price_paise": 5000,
        "stock": 10,
        "category_id": str(category_id),
        "image_urls": ["https://example.com/candle.jpg"]
    }
    response = await client.post("/api/v1/products", json=payload, headers=seller_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Scented Candle"
    assert data["price_paise"] == 5000
    assert data["stock"] == 10
    assert data["image_urls"] == ["https://example.com/candle.jpg"]
    assert "shop_name" in data

    # Verify audit log entry
    prod_id = data["id"]
    audit_res = await db.execute(select(AuditLog).where(AuditLog.event_type == "product.created"))
    audit_log = audit_res.scalar_one_or_none()
    assert audit_log is not None
    assert audit_log.details.get("target_id") == prod_id

@pytest.mark.asyncio
async def test_create_product_price_too_low(client: AsyncClient, seller_headers: dict, category_id: uuid.UUID):
    payload = {
        "title": "Cheap Candle",
        "description": "Too cheap",
        "price_paise": 50, # Minimum is 100
        "stock": 5,
        "category_id": str(category_id)
    }
    response = await client.post("/api/v1/products", json=payload, headers=seller_headers)
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_create_product_price_too_high(client: AsyncClient, seller_headers: dict, category_id: uuid.UUID):
    payload = {
        "title": "Expensive Candle",
        "description": "Too expensive",
        "price_paise": 2000000, # Maximum is 1_000_000
        "stock": 5,
        "category_id": str(category_id)
    }
    response = await client.post("/api/v1/products", json=payload, headers=seller_headers)
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_create_product_stock_negative(client: AsyncClient, seller_headers: dict, category_id: uuid.UUID):
    payload = {
        "title": "Ghost Candle",
        "description": "Negative stock",
        "price_paise": 1500,
        "stock": -1, # Minimum is 0
        "category_id": str(category_id)
    }
    response = await client.post("/api/v1/products", json=payload, headers=seller_headers)
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_create_product_buyer_forbidden(client: AsyncClient, buyer_headers: dict, category_id: uuid.UUID):
    payload = {
        "title": "Buyer Candle",
        "description": "A buyer tries to sell",
        "price_paise": 1500,
        "stock": 5,
        "category_id": str(category_id)
    }
    response = await client.post("/api/v1/products", json=payload, headers=buyer_headers)
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_create_product_invalid_category(client: AsyncClient, seller_headers: dict):
    payload = {
        "title": "Invalid Cat Candle",
        "description": "No such category",
        "price_paise": 1500,
        "stock": 5,
        "category_id": str(uuid.uuid4())
    }
    response = await client.post("/api/v1/products", json=payload, headers=seller_headers)
    assert response.status_code == 400
    assert "Category not found" in response.json()["detail"]

# ==========================================
# PATCH /api/v1/products/{id} (Update Endpoint)
# ==========================================

@pytest.fixture
async def existing_product(client: AsyncClient, seller_headers: dict, category_id: uuid.UUID) -> dict:
    payload = {
        "title": "Initial Product",
        "description": "Initial Description",
        "price_paise": 1000,
        "stock": 5,
        "category_id": str(category_id)
    }
    res = await client.post("/api/v1/products", json=payload, headers=seller_headers)
    return res.json()

@pytest.mark.asyncio
async def test_update_product_success(client: AsyncClient, seller_headers: dict, existing_product: dict, db):
    prod_id = existing_product["id"]
    payload = {
        "title": "Updated Title",
        "price_paise": 2500
    }
    response = await client.patch(f"/api/v1/products/{prod_id}", json=payload, headers=seller_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["price_paise"] == 2500
    assert data["description"] == "Initial Description" # Kept original

    # Verify audit log
    audit_res = await db.execute(select(AuditLog).where(AuditLog.event_type == "product.updated"))
    audit_log = audit_res.scalar_one_or_none()
    assert audit_log is not None
    assert audit_log.details.get("target_id") == prod_id

@pytest.mark.asyncio
async def test_update_product_price_too_low(client: AsyncClient, seller_headers: dict, existing_product: dict):
    prod_id = existing_product["id"]
    payload = {"price_paise": 50}
    response = await client.patch(f"/api/v1/products/{prod_id}", json=payload, headers=seller_headers)
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_update_product_stock_negative(client: AsyncClient, seller_headers: dict, existing_product: dict):
    prod_id = existing_product["id"]
    payload = {"stock": -5}
    response = await client.patch(f"/api/v1/products/{prod_id}", json=payload, headers=seller_headers)
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_update_product_buyer_forbidden(client: AsyncClient, buyer_headers: dict, existing_product: dict):
    prod_id = existing_product["id"]
    payload = {"title": "Forbidden update"}
    response = await client.patch(f"/api/v1/products/{prod_id}", json=payload, headers=buyer_headers)
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_update_product_invalid_category(client: AsyncClient, seller_headers: dict, existing_product: dict):
    prod_id = existing_product["id"]
    payload = {"category_id": str(uuid.uuid4())}
    response = await client.patch(f"/api/v1/products/{prod_id}", json=payload, headers=seller_headers)
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_update_product_not_found(client: AsyncClient, seller_headers: dict):
    fake_id = str(uuid.uuid4())
    payload = {"title": "Update non-existent"}
    response = await client.patch(f"/api/v1/products/{fake_id}", json=payload, headers=seller_headers)
    assert response.status_code == 404

# ==========================================
# DELETE /api/v1/products/{id} (Delete Endpoint)
# ==========================================

@pytest.mark.asyncio
async def test_delete_product_success(client: AsyncClient, seller_headers: dict, existing_product: dict):
    prod_id = existing_product["id"]
    response = await client.delete(f"/api/v1/products/{prod_id}", headers=seller_headers)
    assert response.status_code == 204

@pytest.mark.asyncio
async def test_delete_product_buyer_forbidden(client: AsyncClient, buyer_headers: dict, existing_product: dict):
    prod_id = existing_product["id"]
    response = await client.delete(f"/api/v1/products/{prod_id}", headers=buyer_headers)
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_delete_product_not_found(client: AsyncClient, seller_headers: dict):
    fake_id = str(uuid.uuid4())
    response = await client.delete(f"/api/v1/products/{fake_id}", headers=seller_headers)
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_delete_product_already_deleted(client: AsyncClient, seller_headers: dict, existing_product: dict):
    prod_id = existing_product["id"]
    # First delete
    res1 = await client.delete(f"/api/v1/products/{prod_id}", headers=seller_headers)
    assert res1.status_code == 204
    # Second delete
    res2 = await client.delete(f"/api/v1/products/{prod_id}", headers=seller_headers)
    assert res2.status_code == 404

@pytest.mark.asyncio
async def test_delete_product_audit_logged(client: AsyncClient, seller_headers: dict, existing_product: dict, db):
    prod_id = existing_product["id"]
    await client.delete(f"/api/v1/products/{prod_id}", headers=seller_headers)
    
    # Check audit log
    audit_res = await db.execute(select(AuditLog).where(AuditLog.event_type == "product.deleted"))
    audit_log = audit_res.scalar_one_or_none()
    assert audit_log is not None
    assert audit_log.details.get("target_id") == prod_id

@pytest.mark.asyncio
async def test_delete_product_unauthenticated(client: AsyncClient, existing_product: dict):
    prod_id = existing_product["id"]
    response = await client.delete(f"/api/v1/products/{prod_id}")
    assert response.status_code == 401

# ==========================================
# Additional constraints & flows
# ==========================================

@pytest.mark.asyncio
async def test_update_product_different_seller(client: AsyncClient, seller_headers: dict, existing_product: dict, db):
    # Setup a second seller
    from tests.conftest import create_user_token_helper
    seller_b_token = await create_user_token_helper(client, "seller")
    seller_b_headers = {"Authorization": f"Bearer {seller_b_token}"}

    prod_id = existing_product["id"]
    payload = {"title": "Hijacked update"}
    # Seller B tries to edit Seller A's product -> 404
    response = await client.patch(f"/api/v1/products/{prod_id}", json=payload, headers=seller_b_headers)
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_public_get_after_delete(client: AsyncClient, seller_headers: dict, existing_product: dict):
    prod_id = existing_product["id"]
    
    # Verify we can read it initially as public (no auth)
    res_pub1 = await client.get(f"/api/v1/products/{prod_id}")
    assert res_pub1.status_code == 200
    assert res_pub1.json()["title"] == "Initial Product"
    
    # Soft delete it
    res_del = await client.delete(f"/api/v1/products/{prod_id}", headers=seller_headers)
    assert res_del.status_code == 204
    
    # Verify reading it as public now returns 404
    res_pub2 = await client.get(f"/api/v1/products/{prod_id}")
    assert res_pub2.status_code == 404

# ==========================================
# list_my_products pagination tests
# ==========================================

@pytest.mark.asyncio
async def test_list_my_products_pagination(client: AsyncClient, seller_headers: dict, category_id: uuid.UUID):
    # Create multiple products
    for i in range(5):
        payload = {
            "title": f"Product {i}",
            "description": "Candle item",
            "price_paise": 1000 + i,
            "stock": 10,
            "category_id": str(category_id)
        }
        await client.post("/api/v1/products", json=payload, headers=seller_headers)

    # Get my products with limit=2
    res = await client.get("/api/v1/products/mine?limit=2", headers=seller_headers)
    assert res.status_code == 200
    products = res.json()
    assert len(products) == 2
    # Ensure they are sorted by created_at desc (newest first)
    assert products[0]["title"] == "Product 4"
    assert products[1]["title"] == "Product 3"
