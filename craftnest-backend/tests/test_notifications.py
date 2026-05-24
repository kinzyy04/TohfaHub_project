"""
Tests for the in-app notification system.

Covers:
1. order.received  — placed order triggers seller notifications.
2. order.shipped   — seller status advance triggers buyer notification.
3. order.delivered — seller status advance triggers buyer notification.
4. review.received — submitting a review triggers seller notification.
5. GET /api/v1/notifications — returns latest 20, correct unread_count.
6. POST /api/v1/notifications/read — marks all read.
7. POST /api/v1/notifications/read with ids — selective mark-read.
8. Unauthenticated access returns 401.
"""

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.future import select

from app.models.user import User
from app.models.category import Category
from app.models.product import Product
from app.models.order import Order, OrderItem
from app.models.notification import Notification


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def seller_headers(seller_token: str) -> dict:
    return {"Authorization": f"Bearer {seller_token}"}


@pytest.fixture
async def buyer_headers(buyer_token: str) -> dict:
    return {"Authorization": f"Bearer {buyer_token}"}


@pytest.fixture
async def test_category(db) -> Category:
    cat = Category(
        slug=f"notif-cat-{uuid.uuid4().hex[:8]}",
        display_name="Notification Test Category",
        description="Category for notification tests",
        icon_emoji="🔔",
    )
    db.add(cat)
    await db.flush()
    return cat


@pytest.fixture
async def seller_user(db) -> User:
    res = await db.execute(select(User).where(User.role == "seller"))
    user = res.scalars().first()
    assert user is not None
    return user


@pytest.fixture
async def buyer_user(db) -> User:
    res = await db.execute(select(User).where(User.role == "buyer"))
    user = res.scalars().first()
    assert user is not None
    return user


@pytest.fixture
async def test_product(db, test_category, seller_user) -> Product:
    prod = Product(
        seller_id=seller_user.id,
        category_id=test_category.id,
        title="Notification Test Product",
        description="A product used for notification testing",
        price_paise=1000,
        stock=100,
        image_urls=["https://example.com/notif.jpg"],
        is_active=True,
    )
    db.add(prod)
    await db.flush()
    return prod


# ---------------------------------------------------------------------------
# Helper: place an order via API
# ---------------------------------------------------------------------------

async def place_order(client: AsyncClient, buyer_headers: dict, product: Product) -> dict:
    res = await client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": str(product.id), "quantity": 1}],
            "shipping_address": "123 Test Street, Notification City",
        },
        headers=buyer_headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


# ---------------------------------------------------------------------------
# Test 1: order.received — seller gets notified when buyer places order
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_order_received_notification(
    client: AsyncClient,
    buyer_headers: dict,
    seller_headers: dict,
    test_product: Product,
    seller_user: User,
    db,
):
    await place_order(client, buyer_headers, test_product)

    # Verify a notification was created for the seller
    q = select(Notification).where(
        Notification.user_id == seller_user.id,
        Notification.type == "order.received",
    )
    result = await db.execute(q)
    notifs = result.scalars().all()
    assert len(notifs) >= 1
    notif = notifs[-1]  # latest
    assert notif.title == "New order!"
    assert "Notification Test Product" in notif.body
    assert notif.is_read is False
    assert notif.related_id is not None


# ---------------------------------------------------------------------------
# Test 2 & 3: order.shipped / order.delivered — buyer gets notified
# ---------------------------------------------------------------------------

@pytest.fixture
async def placed_order(client: AsyncClient, buyer_headers: dict, test_product: Product) -> dict:
    return await place_order(client, buyer_headers, test_product)


@pytest.mark.asyncio
async def test_order_shipped_notification(
    client: AsyncClient,
    buyer_headers: dict,
    seller_headers: dict,
    test_product: Product,
    placed_order: dict,
    buyer_user: User,
    db,
):
    order_id = placed_order["id"]

    # Advance to processing first (awaiting_payment → processing)
    res = await client.patch(
        f"/api/v1/seller/orders/{order_id}/status",
        json={"status": "processing"},
        headers=seller_headers,
    )
    assert res.status_code == 200

    # Advance to shipped (processing → shipped)
    res = await client.patch(
        f"/api/v1/seller/orders/{order_id}/status",
        json={"status": "shipped", "tracking_code": "TRK-NOTIF-123"},
        headers=seller_headers,
    )
    assert res.status_code == 200

    # Verify buyer received a notification
    q = select(Notification).where(
        Notification.user_id == buyer_user.id,
        Notification.type == "order.shipped",
    )
    result = await db.execute(q)
    notifs = result.scalars().all()
    assert len(notifs) >= 1
    notif = notifs[-1]
    assert notif.title == "Your order is on the way"
    assert "TRK-NOTIF-123" in notif.body
    assert notif.related_id == uuid.UUID(order_id)


@pytest.mark.asyncio
async def test_order_delivered_notification(
    client: AsyncClient,
    buyer_headers: dict,
    seller_headers: dict,
    test_product: Product,
    placed_order: dict,
    buyer_user: User,
    db,
):
    order_id = placed_order["id"]

    # Advance: processing → shipped → delivered
    for step in [
        {"status": "processing"},
        {"status": "shipped", "tracking_code": "TRK-DEL-001"},
    ]:
        r = await client.patch(
            f"/api/v1/seller/orders/{order_id}/status",
            json=step,
            headers=seller_headers,
        )
        assert r.status_code == 200

    res = await client.patch(
        f"/api/v1/seller/orders/{order_id}/status",
        json={"status": "delivered"},
        headers=seller_headers,
    )
    assert res.status_code == 200

    # Verify buyer received a delivered notification
    q = select(Notification).where(
        Notification.user_id == buyer_user.id,
        Notification.type == "order.delivered",
    )
    result = await db.execute(q)
    notifs = result.scalars().all()
    assert len(notifs) >= 1
    notif = notifs[-1]
    assert notif.title == "Order delivered!"
    assert "review" in notif.body.lower()


# ---------------------------------------------------------------------------
# Test 4: review.received — seller notified when review is posted
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_review_received_notification(
    client: AsyncClient,
    buyer_headers: dict,
    seller_headers: dict,
    test_product: Product,
    placed_order: dict,
    seller_user: User,
    db,
):
    order_id = placed_order["id"]

    # Drive order to delivered so review is allowed
    steps = [
        {"status": "processing"},
        {"status": "shipped", "tracking_code": "TRK-REV-001"},
        {"status": "delivered"},
    ]
    for step in steps:
        r = await client.patch(
            f"/api/v1/seller/orders/{order_id}/status",
            json=step,
            headers=seller_headers,
        )
        assert r.status_code == 200

    # Post a review
    res = await client.post(
        f"/api/v1/products/{test_product.id}/reviews",
        json={"rating": 5, "body": "Amazing product!"},
        headers=buyer_headers,
    )
    assert res.status_code == 201, res.text

    # Verify seller received review.received notification
    q = select(Notification).where(
        Notification.user_id == seller_user.id,
        Notification.type == "review.received",
    )
    result = await db.execute(q)
    notifs = result.scalars().all()
    assert len(notifs) >= 1
    notif = notifs[-1]
    assert notif.title == "New review!"
    assert "5" in notif.body
    assert notif.related_id == test_product.id


# ---------------------------------------------------------------------------
# Test 5: GET /api/v1/notifications — list + unread_count
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_notifications(
    client: AsyncClient,
    buyer_headers: dict,
    seller_headers: dict,
    test_product: Product,
    seller_user: User,
    db,
):
    # Seed 3 notifications directly in DB for the seller
    for i in range(3):
        n = Notification(
            user_id=seller_user.id,
            type="order.received",
            title=f"Test Notification {i}",
            body=f"Body text {i}",
            is_read=False,
        )
        db.add(n)
    await db.flush()

    res = await client.get("/api/v1/notifications", headers=seller_headers)
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "unread_count" in data
    assert data["unread_count"] >= 3
    assert len(data["items"]) <= 20

    # Verify returned items have expected fields
    for item in data["items"]:
        assert "id" in item
        assert "type" in item
        assert "title" in item
        assert "body" in item
        assert "is_read" in item
        assert "created_at" in item


# ---------------------------------------------------------------------------
# Test 6: POST /api/v1/notifications/read — mark ALL read
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mark_all_read(
    client: AsyncClient,
    seller_headers: dict,
    seller_user: User,
    db,
):
    # Seed 2 unread notifications
    for i in range(2):
        n = Notification(
            user_id=seller_user.id,
            type="order.received",
            title=f"Unread {i}",
            body="Will be marked read",
            is_read=False,
        )
        db.add(n)
    await db.flush()

    # Verify unread_count > 0
    res_before = await client.get("/api/v1/notifications", headers=seller_headers)
    assert res_before.json()["unread_count"] >= 2

    # Mark all read (empty body = mark all)
    res = await client.post("/api/v1/notifications/read", json={}, headers=seller_headers)
    assert res.status_code == 200
    assert res.json()["marked_read"] >= 2

    # Verify unread_count is now 0
    res_after = await client.get("/api/v1/notifications", headers=seller_headers)
    assert res_after.json()["unread_count"] == 0


# ---------------------------------------------------------------------------
# Test 7: POST /api/v1/notifications/read with ids — selective mark-read
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mark_selective_read(
    client: AsyncClient,
    seller_headers: dict,
    seller_user: User,
    db,
):
    # Seed 3 unread notifications
    created = []
    for i in range(3):
        n = Notification(
            user_id=seller_user.id,
            type="order.received",
            title=f"Selective {i}",
            body="Selective body",
            is_read=False,
        )
        db.add(n)
        created.append(n)
    await db.flush()

    # Pick first 2 IDs
    target_ids = [str(created[0].id), str(created[1].id)]

    # Mark only those 2 as read
    res = await client.post(
        "/api/v1/notifications/read",
        json={"ids": target_ids},
        headers=seller_headers,
    )
    assert res.status_code == 200
    assert res.json()["marked_read"] == 2

    # Verify 3rd notification is still unread
    await db.refresh(created[2])
    assert created[2].is_read is False

    # Verify first 2 are now read
    await db.refresh(created[0])
    await db.refresh(created[1])
    assert created[0].is_read is True
    assert created[1].is_read is True


# ---------------------------------------------------------------------------
# Test 8: Unauthenticated access returns 401
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unauthenticated_access(client: AsyncClient):
    res_get = await client.get("/api/v1/notifications")
    assert res_get.status_code == 401

    res_post = await client.post("/api/v1/notifications/read", json={})
    assert res_post.status_code == 401
