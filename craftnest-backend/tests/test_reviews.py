"""
Tests for the review system:
  POST /api/v1/products/{id}/reviews
  GET  /api/v1/products/{id}/reviews
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.future import select

from app.models.user import User
from app.models.product import Product
from app.models.category import Category
from app.models.order import Order, OrderItem
from app.models.audit_log import AuditLog


# ---------------------------------------------------------------------------
# Shared fixture: delivers an order so the buyer qualifies to review
# ---------------------------------------------------------------------------

@pytest.fixture
async def review_setup(client: AsyncClient, buyer_token: str, seller_token: str, db_session):
    """
    Creates a product, places an order as the buyer, then walks it all the
    way to 'delivered' via seller endpoints.  Returns a dict with all the
    IDs/tokens needed by the review tests.
    """
    res = await db_session.execute(select(User).where(User.role == "seller"))
    seller = res.scalars().first()

    category = Category(slug="review-test-cat", display_name="Review Cat", description="desc")
    db_session.add(category)
    await db_session.flush()

    product = Product(
        seller_id=seller.id,
        category_id=category.id,
        title="Hand-Carved Bowl",
        description="Beautiful craft",
        price_paise=4000,
        stock=5,
        is_active=True,
    )
    db_session.add(product)
    await db_session.flush()

    # Place order as buyer
    order_resp = await client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": str(product.id), "quantity": 1}],
            "shipping_address": "99 Artisan Lane, Jaipur",
        },
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert order_resp.status_code == 201
    order_id = order_resp.json()["id"]

    # Seller: awaiting_payment → processing → shipped → delivered
    seller_h = {"Authorization": f"Bearer {seller_token}"}
    base = f"/api/v1/seller/orders/{order_id}/status"

    r = await client.patch(base, json={"status": "processing"}, headers=seller_h)
    assert r.status_code == 200
    r = await client.patch(base, json={"status": "shipped", "tracking_code": "TRK-001"}, headers=seller_h)
    assert r.status_code == 200
    r = await client.patch(base, json={"status": "delivered"}, headers=seller_h)
    assert r.status_code == 200

    return {
        "product": product,
        "product_id": str(product.id),
        "order_id": order_id,
        "buyer_token": buyer_token,
        "seller_token": seller_token,
    }


# ---------------------------------------------------------------------------
# Happy path: delivered order → successful review
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_review_happy_path(
    client: AsyncClient, review_setup, buyer_token: str, db_session
):
    """Buyer with a delivered order can leave a review. avg_rating and review_count update."""
    setup = review_setup
    product = setup["product"]

    resp = await client.post(
        f"/api/v1/products/{setup['product_id']}/reviews",
        json={"rating": 5, "body": "Absolutely beautiful, worth every paise!"},
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["rating"] == 5
    assert data["body"] == "Absolutely beautiful, worth every paise!"
    assert data["product_id"] == setup["product_id"]

    # avg_rating and review_count should be updated
    await db_session.refresh(product)
    assert product.review_count == 1
    assert float(product.avg_rating) == 5.0

    # Audit log should exist
    audit_res = await db_session.execute(
        select(AuditLog).where(AuditLog.event_type == "review.created")
    )
    audit = audit_res.scalar_one_or_none()
    assert audit is not None
    assert audit.details["product_id"] == setup["product_id"]
    assert audit.details["rating"] == 5


# ---------------------------------------------------------------------------
# GET /reviews — public, paginated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_product_reviews(client: AsyncClient, review_setup, buyer_token: str):
    """Public GET returns the review after it is created."""
    setup = review_setup

    await client.post(
        f"/api/v1/products/{setup['product_id']}/reviews",
        json={"rating": 4},
        headers={"Authorization": f"Bearer {buyer_token}"},
    )

    resp = await client.get(f"/api/v1/products/{setup['product_id']}/reviews")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["rating"] == 4


# ---------------------------------------------------------------------------
# Not-delivered → 422
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_review_not_delivered_422(
    client: AsyncClient, buyer_token: str, seller_token: str, db_session
):
    """Buyer with a non-delivered order cannot review the product."""
    res = await db_session.execute(select(User).where(User.role == "seller"))
    seller = res.scalars().first()

    category = Category(slug="nd-review-cat", display_name="ND Cat", description="desc")
    db_session.add(category)
    await db_session.flush()

    product = Product(
        seller_id=seller.id,
        category_id=category.id,
        title="Undelivered Bowl",
        description="desc",
        price_paise=2000,
        stock=5,
        is_active=True,
    )
    db_session.add(product)
    await db_session.flush()

    # Place order but do NOT advance to delivered
    order_resp = await client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": str(product.id), "quantity": 1}],
            "shipping_address": "Somewhere",
        },
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert order_resp.status_code == 201

    resp = await client.post(
        f"/api/v1/products/{str(product.id)}/reviews",
        json={"rating": 3},
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert resp.status_code == 422
    assert "delivered" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Duplicate review → 422
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_review_duplicate_422(
    client: AsyncClient, review_setup, buyer_token: str
):
    """Reviewing the same product twice returns 422."""
    setup = review_setup
    url = f"/api/v1/products/{setup['product_id']}/reviews"
    headers = {"Authorization": f"Bearer {buyer_token}"}

    r1 = await client.post(url, json={"rating": 5}, headers=headers)
    assert r1.status_code == 201

    r2 = await client.post(url, json={"rating": 4}, headers=headers)
    assert r2.status_code == 422
    assert "already reviewed" in r2.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Non-buyer → 403
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_review_non_buyer_403(
    client: AsyncClient, review_setup, seller_token: str
):
    """A seller attempting to post a review gets 403."""
    setup = review_setup
    resp = await client.post(
        f"/api/v1/products/{setup['product_id']}/reviews",
        json={"rating": 5},
        headers={"Authorization": f"Bearer {seller_token}"},
    )
    assert resp.status_code == 403
