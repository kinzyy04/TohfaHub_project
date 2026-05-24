import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.future import select
from app.models.audit_log import AuditLog
from app.services.admin_service import clear_stats_cache
from app.models.user import User
from app.models.product import Product
from app.models.reel import Reel
from app.models.category import Category
from app.models.order import Order, OrderItem

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


# ---------------------------------------------------------------------------
# GET /api/v1/admin/sellers - list sellers
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_list_sellers(client: AsyncClient, admin_token: str, seller_token: str, db_session):
    res_seller = await db_session.execute(select(User).where(User.role == "seller"))
    seller = res_seller.scalars().first()

    # Add a product to make sure product_count is 1
    category = Category(slug="admin-test-cat", display_name="Admin Test Cat", description="desc")
    db_session.add(category)
    await db_session.flush()

    product = Product(
        seller_id=seller.id,
        category_id=category.id,
        title="Admin Test Product",
        description="Beautiful product",
        price_paise=1000,
        stock=5,
        is_active=True,
    )
    db_session.add(product)
    await db_session.flush()

    # Get sellers list
    response = await client.get(
        "/api/v1/admin/sellers",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    
    # Check that our seller is in the list
    seller_item = next((item for item in data if item["user_id"] == str(seller.id)), None)
    assert seller_item is not None
    assert seller_item["email"] == seller.email
    assert seller_item["is_active"] is True
    assert seller_item["product_count"] == 1
    assert seller_item["order_count"] == 0

    # Search filter test
    response_search = await client.get(
        f"/api/v1/admin/sellers?search={seller.email}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response_search.status_code == 200
    search_data = response_search.json()
    assert len(search_data) == 1
    assert search_data[0]["user_id"] == str(seller.id)


# ---------------------------------------------------------------------------
# GET /api/v1/admin/sellers/{user_id} - seller details
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_get_seller_details(client: AsyncClient, admin_token: str, seller_token: str, db_session):
    res_seller = await db_session.execute(select(User).where(User.role == "seller"))
    seller = res_seller.scalars().first()

    response = await client.get(
        f"/api/v1/admin/sellers/{seller.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["id"] == str(seller.id)
    assert "products" in data
    assert "recent_orders" in data


# ---------------------------------------------------------------------------
# POST /api/v1/admin/sellers/{user_id}/ban & /unban
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_ban_unban_seller(client: AsyncClient, admin_token: str, seller_token: str, db_session):
    # Fetch seller
    res_seller = await db_session.execute(select(User).where(User.role == "seller"))
    seller = res_seller.scalars().first()

    # Create category, product, and reel to verify cascading status changes
    category = Category(slug="ban-test-cat", display_name="Ban Cat", description="desc")
    db_session.add(category)
    await db_session.flush()

    product = Product(
        seller_id=seller.id,
        category_id=category.id,
        title="Ban Test Product",
        description="To be hidden",
        price_paise=2500,
        stock=10,
        is_active=True,
    )
    db_session.add(product)
    await db_session.flush()

    reel = Reel(
        seller_id=seller.id,
        product_id=product.id,
        video_url="/media/reels/test.mp4",
        thumbnail_url="/media/reels/test.jpg",
        duration_seconds=15,
        caption="Fun reel",
        is_active=True,
    )
    db_session.add(reel)
    await db_session.flush()

    # 1. Ban the seller
    ban_resp = await client.post(
        f"/api/v1/admin/sellers/{seller.id}/ban",
        json={"reason": "Terms of Service violation"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert ban_resp.status_code == 200
    assert ban_resp.json()["is_active"] is False

    # Verify atomic update
    await db_session.refresh(seller)
    await db_session.refresh(product)
    await db_session.refresh(reel)
    assert seller.is_active is False
    assert product.is_active is False
    assert reel.is_active is False

    # Check products are hidden from browse (e.g. search)
    search_resp = await client.get(f"/api/v1/browse/search?q=Ban")
    assert search_resp.status_code == 200
    search_results = search_resp.json()
    assert not any(p["id"] == str(product.id) for p in search_results)

    # 2. Try to ban again -> 409 Conflict
    ban_again_resp = await client.post(
        f"/api/v1/admin/sellers/{seller.id}/ban",
        json={"reason": "Another reason"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert ban_again_resp.status_code == 409
    assert "already banned" in ban_again_resp.json()["detail"].lower()

    # 3. Try to ban admin -> 403 Forbidden
    admin_user = (await db_session.execute(select(User).where(User.role == "admin"))).scalars().first()
    ban_admin_resp = await client.post(
        f"/api/v1/admin/sellers/{admin_user.id}/ban",
        json={"reason": "Try to ban admin"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert ban_admin_resp.status_code == 403
    assert "cannot be banned" in ban_admin_resp.json()["detail"].lower()

    # 4. Unban the seller
    unban_resp = await client.post(
        f"/api/v1/admin/sellers/{seller.id}/unban",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert unban_resp.status_code == 200
    assert unban_resp.json()["is_active"] is True

    # Verify unbanned state
    await db_session.refresh(seller)
    await db_session.refresh(product)
    await db_session.refresh(reel)
    assert seller.is_active is True
    assert product.is_active is True
    assert reel.is_active is True

    # Check products reappear in browse/search
    search_again_resp = await client.get(f"/api/v1/browse/search?q=Ban")
    assert search_again_resp.status_code == 200
    search_again_results = search_again_resp.json()
    assert any(p["id"] == str(product.id) for p in search_again_results)


# ---------------------------------------------------------------------------
# Goal A — Admin Order Oversight Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_list_orders_filters(client: AsyncClient, admin_token: str, seller_token: str, buyer_token: str, db_session):
    # Retrieve buyer
    res_buyer = await db_session.execute(select(User).where(User.role == "buyer"))
    buyer = res_buyer.scalars().first()

    # Retrieve seller
    res_seller = await db_session.execute(select(User).where(User.role == "seller"))
    seller = res_seller.scalars().first()

    # Set seller profile shop name to Glow Artisans
    from app.models.profile import SellerProfile
    prof_res = await db_session.execute(select(SellerProfile).where(SellerProfile.user_id == seller.id))
    profile = prof_res.scalar_one_or_none()
    if not profile:
        profile = SellerProfile(user_id=seller.id, shop_name="Glow Artisans", shipping_days=3)
        db_session.add(profile)
    else:
        profile.shop_name = "Glow Artisans"
    await db_session.flush()

    # Create category and product
    category = Category(slug="order-oversight-cat", display_name="Oversight Cat", description="desc")
    db_session.add(category)
    await db_session.flush()

    product = Product(
        seller_id=seller.id,
        category_id=category.id,
        title="Oversight Product",
        description="Oversight Product Desc",
        price_paise=1000,
        stock=5,
        is_active=True
    )
    db_session.add(product)
    await db_session.flush()

    # Create an order
    order = Order(
        buyer_id=buyer.id,
        status="awaiting_payment",
        total_paise=1000,
        shipping_address="Test Address"
    )
    db_session.add(order)
    await db_session.flush()

    order_item = OrderItem(
        order_id=order.id,
        product_id=product.id,
        seller_id=seller.id,
        title_snapshot="Oversight Product",
        price_snapshot_paise=1000,
        quantity=1
    )
    db_session.add(order_item)
    await db_session.flush()

    # Query admin orders
    response = await client.get(
        "/api/v1/admin/orders",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    
    order_row = next((o for o in data["items"] if o["id"] == str(order.id)), None)
    assert order_row is not None
    assert order_row["buyer_email"] == buyer.email
    assert "Glow Artisans" in order_row["seller_shop_name"]

    # Test query filters
    res_filtered = await client.get(
        f"/api/v1/admin/orders?status=awaiting_payment&buyer_email={buyer.email}&seller_id={seller.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res_filtered.status_code == 200
    assert res_filtered.json()["total"] >= 1


@pytest.mark.asyncio
async def test_admin_force_order_status(client: AsyncClient, admin_token: str, buyer_token: str, db_session):
    res_buyer = await db_session.execute(select(User).where(User.role == "buyer"))
    buyer = res_buyer.scalars().first()

    order = Order(
        buyer_id=buyer.id,
        status="awaiting_payment",
        total_paise=500,
        shipping_address="Address"
    )
    db_session.add(order)
    await db_session.flush()

    # Force status update
    response = await client.patch(
        f"/api/v1/admin/orders/{order.id}/status",
        json={"status": "processing", "admin_note": "Unsticking order"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "processing"
    assert "Unsticking order" in response.json()["seller_note"]

    # Verify audit log
    audit_res = await db_session.execute(
        select(AuditLog).where(AuditLog.event_type == "admin.order.status_override")
    )
    audit = audit_res.scalar_one_or_none()
    assert audit is not None
    assert audit.details["from"] == "awaiting_payment"
    assert audit.details["to"] == "processing"
    assert audit.details["admin_note"] == "Unsticking order"


@pytest.mark.asyncio
async def test_admin_flag_order_refund(client: AsyncClient, admin_token: str, buyer_token: str, db_session):
    res_buyer = await db_session.execute(select(User).where(User.role == "buyer"))
    buyer = res_buyer.scalars().first()

    order = Order(
        buyer_id=buyer.id,
        status="delivered",
        total_paise=2500,
        shipping_address="Address"
    )
    db_session.add(order)
    await db_session.flush()

    # Flag for refund
    response = await client.post(
        f"/api/v1/admin/orders/{order.id}/refund_flag",
        json={"note": "Defective item reported by customer"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "refunded"
    assert "Defective item" in response.json()["seller_note"]

    # Verify audit log
    audit_res = await db_session.execute(
        select(AuditLog).where(AuditLog.event_type == "admin.order.refund_flagged")
    )
    audit = audit_res.scalar_one_or_none()
    assert audit is not None
    assert audit.details["note"] == "Defective item reported by customer"


# ---------------------------------------------------------------------------
# Goal B — Category Management Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_category_lifecycle(client: AsyncClient, admin_token: str, db_session):
    # 1. Create category
    create_payload = {
        "slug": "woodworking",
        "display_name": "Woodworking",
        "description": "Hand-carved wood products",
        "icon_emoji": "🪵",
        "sort_order": 5
    }
    response = await client.post(
        "/api/v1/admin/categories",
        json=create_payload,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["slug"] == "woodworking"
    assert data["icon_emoji"] == "🪵"

    # Verify audit log
    audit_res = await db_session.execute(
        select(AuditLog).where(AuditLog.event_type == "admin.category.created")
    )
    audit = audit_res.scalar_one_or_none()
    assert audit is not None
    assert audit.details["slug"] == "woodworking"

    # Test duplicate slug -> 409
    response_dup = await client.post(
        "/api/v1/admin/categories",
        json=create_payload,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response_dup.status_code == 409

    # 2. Update category
    cat_id = data["id"]
    update_payload = {
        "display_name": "Fine Woodworking",
        "icon_emoji": "🪓"
    }
    response_update = await client.patch(
        f"/api/v1/admin/categories/{cat_id}",
        json=update_payload,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response_update.status_code == 200
    assert response_update.json()["display_name"] == "Fine Woodworking"
    assert response_update.json()["icon_emoji"] == "🪓"


@pytest.mark.asyncio
async def test_admin_category_soft_delete(client: AsyncClient, admin_token: str, db_session):
    category = Category(
        slug="temporary-cat",
        display_name="Temporary Category",
        description="Will be soft deleted",
        is_active=True
    )
    db_session.add(category)
    await db_session.flush()

    # Soft delete category
    response = await client.delete(
        f"/api/v1/admin/categories/{category.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200

    # Verify is_active is False
    await db_session.refresh(category)
    assert category.is_active is False

    # Verify audit log
    audit_res = await db_session.execute(
        select(AuditLog).where(AuditLog.event_type == "admin.category.deleted")
    )
    assert audit_res.scalar_one_or_none() is not None

    # Check it does NOT show in public browse categories
    browse_resp = await client.get("/api/v1/browse/categories")
    assert browse_resp.status_code == 200
    assert not any(c["id"] == str(category.id) for c in browse_resp.json())

    # Check it STILL shows in admin list
    admin_list_resp = await client.get(
        "/api/v1/admin/categories",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert admin_list_resp.status_code == 200
    assert any(c["id"] == str(category.id) for c in admin_list_resp.json())


@pytest.mark.asyncio
async def test_admin_category_delete_prevention(client: AsyncClient, admin_token: str, seller_token: str, db_session):
    category = Category(slug="locked-cat", display_name="Locked Cat", description="desc", is_active=True)
    db_session.add(category)
    await db_session.flush()

    # Add a product to the category
    res_seller = await db_session.execute(select(User).where(User.role == "seller"))
    seller = res_seller.scalars().first()

    product = Product(
        seller_id=seller.id,
        category_id=category.id,
        title="Cat Product",
        description="desc",
        price_paise=1000,
        stock=1,
        is_active=True
    )
    db_session.add(product)
    await db_session.flush()

    # Attempt delete category containing product -> 409
    response = await client.delete(
        f"/api/v1/admin/categories/{category.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 409
    assert "associated products" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Goal C — Toggle Sponsored Status Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_toggle_product_sponsored(client: AsyncClient, admin_token: str, seller_token: str, db_session):
    # Fetch a product
    res_seller = await db_session.execute(select(User).where(User.role == "seller"))
    seller = res_seller.scalars().first()

    category = Category(slug="sponsored-test-cat", display_name="Cat", description="desc")
    db_session.add(category)
    await db_session.flush()

    product = Product(
        seller_id=seller.id,
        category_id=category.id,
        title="Vanilla Candle",
        description="Smells nice",
        price_paise=1500,
        stock=10,
        is_active=True,
        is_sponsored=False
    )
    db_session.add(product)
    await db_session.flush()

    # Toggle to true
    response = await client.patch(
        f"/api/v1/admin/products/{product.id}/sponsored",
        json={"is_sponsored": True},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    assert response.json()["is_sponsored"] is True

    # Verify audit log
    audit_res = await db_session.execute(
        select(AuditLog).where(AuditLog.event_type == "admin.product.sponsored_toggled")
    )
    audit = audit_res.scalar_one_or_none()
    assert audit is not None
    assert audit.details["is_sponsored"] is True

