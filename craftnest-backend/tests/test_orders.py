import pytest
from app.models.order import Order, OrderItem
from app.models.user import User
from app.models.product import Product
from app.models.category import Category
from app.models.audit_log import AuditLog
import uuid
import asyncio
from httpx import AsyncClient
from sqlalchemy.future import select

@pytest.mark.asyncio
async def test_create_order_models(db_session):
    # Create buyer
    buyer = User(email="buyer_orders@example.com", password_hash="hash", full_name="Buyer", role="buyer")
    db_session.add(buyer)
    
    # Create seller
    seller = User(email="seller_orders@example.com", password_hash="hash", full_name="Seller", role="seller")
    db_session.add(seller)
    
    # Create category
    category = Category(slug="order-test", display_name="Order Test", description="Test")
    db_session.add(category)
    await db_session.flush()
    
    # Create product
    product = Product(
        seller_id=seller.id,
        category_id=category.id,
        title="Test Product",
        description="A product",
        price_paise=1000,
        stock=5
    )
    db_session.add(product)
    await db_session.flush()
    
    # Create order
    order = Order(
        buyer_id=buyer.id,
        status="pending",
        total_paise=2000,
        shipping_address="123 Test St",
        seller_note="Please ship fast"
    )
    db_session.add(order)
    await db_session.flush()
    
    # Create order item
    order_item = OrderItem(
        order_id=order.id,
        product_id=product.id,
        seller_id=seller.id,
        title_snapshot="Test Product",
        price_snapshot_paise=1000
    )
    db_session.add(order_item)
    await db_session.flush()
    
    assert order.id is not None
    assert order.buyer_id == buyer.id
    assert order_item.id is not None
    assert order_item.order_id == order.id
    assert order_item.seller_id == seller.id


@pytest.fixture
async def order_setup(db_session):
    category = Category(slug="candle-category", display_name="Candles", description="Candles description")
    db_session.add(category)
    await db_session.flush()
    return category.id


@pytest.mark.asyncio
async def test_create_order_happy_path(client: AsyncClient, buyer_token: str, seller_token: str, order_setup, db_session):
    category_id = order_setup
    
    res_seller = await db_session.execute(select(User).where(User.role == "seller"))
    seller = res_seller.scalars().first()
    
    product1 = Product(
        seller_id=seller.id,
        category_id=category_id,
        title="Vanilla Candle",
        description="Smells nice",
        price_paise=1500,
        stock=10,
        is_active=True
    )
    product2 = Product(
        seller_id=seller.id,
        category_id=category_id,
        title="Lavender Candle",
        description="Very relaxing",
        price_paise=2000,
        stock=20,
        is_active=True
    )
    db_session.add_all([product1, product2])
    await db_session.flush()
    
    headers = {"Authorization": f"Bearer {buyer_token}"}
    payload = {
        "items": [
            {"product_id": str(product1.id), "quantity": 2},
            {"product_id": str(product2.id), "quantity": 1}
        ],
        "shipping_address": "flat 3, Rose Apartments, Jodhpur 342001"
    }
    
    resp = await client.post("/api/v1/orders", json=payload, headers=headers)
    assert resp.status_code == 201
    
    data = resp.json()
    assert data["status"] == "awaiting_payment"
    assert data["total_paise"] == (1500 * 2) + (2000 * 1)
    assert data["shipping_address"] == "flat 3, Rose Apartments, Jodhpur 342001"
    assert len(data["items"]) == 2
    
    await db_session.refresh(product1)
    await db_session.refresh(product2)
    assert product1.stock == 8
    assert product2.stock == 19
    
    audit_res = await db_session.execute(
        select(AuditLog).where(AuditLog.event_type == "order.created")
    )
    audit_log = audit_res.scalar_one_or_none()
    assert audit_log is not None
    assert audit_log.details.get("target_id") == data["id"]


@pytest.mark.asyncio
async def test_create_order_stock_exhaustion(client: AsyncClient, buyer_token: str, seller_token: str, order_setup, db_session):
    category_id = order_setup
    res_seller = await db_session.execute(select(User).where(User.role == "seller"))
    seller = res_seller.scalars().first()
    
    product = Product(
        seller_id=seller.id,
        category_id=category_id,
        title="Limited Candle",
        description="Only 1 left",
        price_paise=1500,
        stock=1,
        is_active=True
    )
    db_session.add(product)
    await db_session.flush()
    
    headers = {"Authorization": f"Bearer {buyer_token}"}
    payload = {
        "items": [
            {"product_id": str(product.id), "quantity": 2}
        ],
        "shipping_address": "flat 3, Rose Apartments, Jodhpur 342001"
    }
    
    resp = await client.post("/api/v1/orders", json=payload, headers=headers)
    assert resp.status_code == 422
    assert str(product.id) in resp.text
    
    await db_session.refresh(product)
    assert product.stock == 1


@pytest.mark.asyncio
async def test_create_order_inactive_product(client: AsyncClient, buyer_token: str, seller_token: str, order_setup, db_session):
    category_id = order_setup
    res_seller = await db_session.execute(select(User).where(User.role == "seller"))
    seller = res_seller.scalars().first()
    
    product = Product(
        seller_id=seller.id,
        category_id=category_id,
        title="Inactive Candle",
        description="Not for sale",
        price_paise=1500,
        stock=10,
        is_active=False
    )
    db_session.add(product)
    await db_session.flush()
    
    headers = {"Authorization": f"Bearer {buyer_token}"}
    payload = {
        "items": [
            {"product_id": str(product.id), "quantity": 1}
        ],
        "shipping_address": "flat 3, Rose Apartments, Jodhpur 342001"
    }
    
    resp = await client.post("/api/v1/orders", json=payload, headers=headers)
    assert resp.status_code == 422
    assert str(product.id) in resp.text


@pytest.mark.asyncio
async def test_create_order_non_buyer_forbidden(client: AsyncClient, seller_token: str, order_setup, db_session):
    category_id = order_setup
    res_seller = await db_session.execute(select(User).where(User.role == "seller"))
    seller = res_seller.scalars().first()
    
    product = Product(
        seller_id=seller.id,
        category_id=category_id,
        title="Candle",
        description="Smells nice",
        price_paise=1500,
        stock=10,
        is_active=True
    )
    db_session.add(product)
    await db_session.flush()
    
    headers = {"Authorization": f"Bearer {seller_token}"}
    payload = {
        "items": [
            {"product_id": str(product.id), "quantity": 1}
        ],
        "shipping_address": "flat 3, Rose Apartments, Jodhpur 342001"
    }
    
    resp = await client.post("/api/v1/orders", json=payload, headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_order_race_condition(client: AsyncClient, engine):
    from app.core.database import get_db, Base
    from app.main import app
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import delete
    from app.models.user import User
    from app.models.product import Product
    from app.models.category import Category
    import uuid
    import asyncio
    
    # 1. Override get_db to yield engine-bound sessions (independent connections)
    async def override_get_db_engine():
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
                
    app.dependency_overrides[get_db] = override_get_db_engine
    
    # 2. Setup seller, category and product using engine-bound session
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        seller = User(
            email="seller_race@example.com",
            password_hash="hash",
            full_name="Seller Race",
            role="seller",
            is_active=True
        )
        session.add(seller)
        category = Category(
            slug="candle-category-race",
            display_name="Candles Race",
            description="Candles description"
        )
        session.add(category)
        await session.flush()
        
        product = Product(
            id=uuid.uuid4(),
            seller_id=seller.id,
            category_id=category.id,
            title="Last Candle",
            description="The very last one",
            price_paise=1500,
            stock=1,
            is_active=True
        )
        session.add(product)
        await session.commit()
        
    try:
        # 3. Create buyer users and get tokens via override_get_db_engine
        from tests.conftest import create_user_token_helper
        buyer_a_token = await create_user_token_helper(client, "buyer")
        buyer_b_token = await create_user_token_helper(client, "buyer")
        
        headers_a = {"Authorization": f"Bearer {buyer_a_token}"}
        headers_b = {"Authorization": f"Bearer {buyer_b_token}"}
        
        payload = {
            "items": [
                {"product_id": str(product.id), "quantity": 1}
            ],
            "shipping_address": "flat 3, Rose Apartments, Jodhpur 342001"
        }
        
        # 4. Perform concurrent requests
        resps = await asyncio.gather(
            client.post("/api/v1/orders", json=payload, headers=headers_a),
            client.post("/api/v1/orders", json=payload, headers=headers_b),
            return_exceptions=True
        )
        
        for r in resps:
            if isinstance(r, Exception):
                raise r
                
        status_codes = [r.status_code for r in resps]
        
        assert 201 in status_codes
        assert 409 in status_codes
        
        failed_resp = next(r for r in resps if r.status_code == 409)
        assert "insufficient stock" in failed_resp.json()["detail"]
        
        # 5. Check database state
        async with AsyncSession(bind=engine) as session:
            res = await session.execute(select(Product).where(Product.id == product.id))
            p = res.scalar_one()
            assert p.stock == 0
            
    finally:
        # 6. Clean up everything from database to avoid pollution
        app.dependency_overrides.clear()
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            for table in reversed(Base.metadata.sorted_tables):
                await session.execute(delete(table))
            await session.commit()


# ===========================================================================
# Seller endpoint tests
# ===========================================================================

@pytest.fixture
async def seller_order_setup(client: AsyncClient, seller_token: str, buyer_token: str, db_session):
    """
    Creates a category, product (owned by the seller fixture user), and a
    buyer order for that product.  Returns a dict with useful IDs/tokens.
    """
    # Resolve the seller user from the DB
    res = await db_session.execute(select(User).where(User.role == "seller"))
    seller = res.scalars().first()

    category = Category(slug="seller-test-cat", display_name="Seller Cat", description="desc")
    db_session.add(category)
    await db_session.flush()

    product = Product(
        seller_id=seller.id,
        category_id=category.id,
        title="Artisan Vase",
        description="Hand-thrown",
        price_paise=3000,
        stock=5,
        is_active=True,
    )
    db_session.add(product)
    await db_session.flush()

    # Place an order as the buyer
    payload = {
        "items": [{"product_id": str(product.id), "quantity": 1}],
        "shipping_address": "123 Craft Street, Jaipur",
    }
    resp = await client.post(
        "/api/v1/orders",
        json=payload,
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert resp.status_code == 201
    order_data = resp.json()

    return {
        "seller": seller,
        "product": product,
        "order_id": order_data["id"],
        "seller_token": seller_token,
        "buyer_token": buyer_token,
    }


@pytest.mark.asyncio
async def test_seller_list_orders_happy_path(
    client: AsyncClient, seller_order_setup, seller_token: str
):
    """Seller sees their order in the paginated list."""
    setup = seller_order_setup
    resp = await client.get(
        "/api/v1/seller/orders",
        headers={"Authorization": f"Bearer {seller_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert data["page"] == 1
    order_ids = [o["id"] for o in data["items"]]
    assert setup["order_id"] in order_ids


@pytest.mark.asyncio
async def test_seller_list_orders_status_filter(
    client: AsyncClient, seller_order_setup, seller_token: str
):
    """Status filter returns only matching orders; non-matching status yields 0."""
    setup = seller_order_setup

    # Should find the order when filtering by its real status
    resp_match = await client.get(
        "/api/v1/seller/orders?status=awaiting_payment",
        headers={"Authorization": f"Bearer {seller_token}"},
    )
    assert resp_match.status_code == 200
    assert resp_match.json()["total"] >= 1

    # Should NOT find the order under a different status
    resp_no = await client.get(
        "/api/v1/seller/orders?status=delivered",
        headers={"Authorization": f"Bearer {seller_token}"},
    )
    assert resp_no.status_code == 200
    order_ids = [o["id"] for o in resp_no.json()["items"]]
    assert setup["order_id"] not in order_ids


@pytest.mark.asyncio
async def test_seller_list_orders_items_scoped(
    client: AsyncClient, seller_order_setup, seller_token: str
):
    """Items in each listed order are scoped to the seller's own items only."""
    setup = seller_order_setup
    resp = await client.get(
        "/api/v1/seller/orders",
        headers={"Authorization": f"Bearer {seller_token}"},
    )
    assert resp.status_code == 200
    for order in resp.json()["items"]:
        for item in order["items"]:
            assert item["seller_id"] == str(setup["seller"].id)


@pytest.mark.asyncio
async def test_seller_get_order_happy_path(
    client: AsyncClient, seller_order_setup, seller_token: str
):
    """Seller can fetch the detail of their order."""
    setup = seller_order_setup
    resp = await client.get(
        f"/api/v1/seller/orders/{setup['order_id']}",
        headers={"Authorization": f"Bearer {seller_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == setup["order_id"]
    # Only seller's items should appear
    for item in data["items"]:
        assert item["seller_id"] == str(setup["seller"].id)


@pytest.mark.asyncio
async def test_seller_get_order_wrong_seller_404(
    client: AsyncClient, seller_order_setup
):
    """A different seller gets 404 for an order that doesn't contain their items."""
    from tests.conftest import create_user_token_helper

    other_seller_token = await create_user_token_helper(client, "seller")
    setup = seller_order_setup

    resp = await client.get(
        f"/api/v1/seller/orders/{setup['order_id']}",
        headers={"Authorization": f"Bearer {other_seller_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_seller_update_status_awaiting_to_processing(
    client: AsyncClient, seller_order_setup, seller_token: str, db_session
):
    """Seller can advance awaiting_payment → processing."""
    setup = seller_order_setup
    resp = await client.patch(
        f"/api/v1/seller/orders/{setup['order_id']}/status",
        json={"status": "processing", "seller_note": "Payment confirmed offline"},
        headers={"Authorization": f"Bearer {seller_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processing"
    assert data["seller_note"] == "Payment confirmed offline"

    # Audit log should be present
    audit_res = await db_session.execute(
        select(AuditLog).where(AuditLog.event_type == "order.status_changed")
    )
    audit = audit_res.scalar_one_or_none()
    assert audit is not None
    assert audit.details["from"] == "awaiting_payment"
    assert audit.details["to"] == "processing"
    assert audit.details["tracking_code"] is None


@pytest.mark.asyncio
async def test_seller_update_status_processing_to_shipped_requires_tracking(
    client: AsyncClient, seller_order_setup, seller_token: str, db_session
):
    """processing → shipped must include tracking_code; missing it → 422."""
    setup = seller_order_setup

    # First advance to processing
    await client.patch(
        f"/api/v1/seller/orders/{setup['order_id']}/status",
        json={"status": "processing"},
        headers={"Authorization": f"Bearer {seller_token}"},
    )

    # Now try shipped without tracking_code
    resp_no_tracking = await client.patch(
        f"/api/v1/seller/orders/{setup['order_id']}/status",
        json={"status": "shipped"},
        headers={"Authorization": f"Bearer {seller_token}"},
    )
    assert resp_no_tracking.status_code == 422
    assert "tracking_code" in resp_no_tracking.json()["detail"]

    # With tracking_code it should succeed
    resp_ok = await client.patch(
        f"/api/v1/seller/orders/{setup['order_id']}/status",
        json={"status": "shipped", "tracking_code": "TRK-12345"},
        headers={"Authorization": f"Bearer {seller_token}"},
    )
    assert resp_ok.status_code == 200
    assert resp_ok.json()["status"] == "shipped"
    assert resp_ok.json()["tracking_code"] == "TRK-12345"

    # Verify audit logs
    audit_res = await db_session.execute(
        select(AuditLog).where(AuditLog.event_type == "order.status_changed")
    )
    audits = audit_res.scalars().all()
    
    # 1. Check processing audit log
    processing_audit = next((a for a in audits if a.details.get("to") == "processing"), None)
    assert processing_audit is not None
    assert processing_audit.details["from"] == "awaiting_payment"
    assert processing_audit.details["to"] == "processing"
    assert processing_audit.details["tracking_code"] is None

    # 2. Check shipped audit log
    shipped_audit = next((a for a in audits if a.details.get("to") == "shipped"), None)
    assert shipped_audit is not None
    assert shipped_audit.details["from"] == "processing"
    assert shipped_audit.details["to"] == "shipped"
    assert shipped_audit.details["tracking_code"] == "TRK-12345"


@pytest.mark.asyncio
async def test_seller_update_status_shipped_to_delivered(
    client: AsyncClient, seller_order_setup, seller_token: str
):
    """Full happy-path chain: awaiting_payment → processing → shipped → delivered."""
    setup = seller_order_setup

    await client.patch(
        f"/api/v1/seller/orders/{setup['order_id']}/status",
        json={"status": "processing"},
        headers={"Authorization": f"Bearer {seller_token}"},
    )
    await client.patch(
        f"/api/v1/seller/orders/{setup['order_id']}/status",
        json={"status": "shipped", "tracking_code": "TRK-99"},
        headers={"Authorization": f"Bearer {seller_token}"},
    )
    resp = await client.patch(
        f"/api/v1/seller/orders/{setup['order_id']}/status",
        json={"status": "delivered"},
        headers={"Authorization": f"Bearer {seller_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "delivered"


@pytest.mark.asyncio
async def test_seller_update_status_invalid_transition(
    client: AsyncClient, seller_order_setup, seller_token: str
):
    """Skipping a step in the state machine → 422 with explanation."""
    setup = seller_order_setup

    # Try to jump directly from awaiting_payment → shipped (skips processing)
    resp = await client.patch(
        f"/api/v1/seller/orders/{setup['order_id']}/status",
        json={"status": "shipped", "tracking_code": "TRK-XYZ"},
        headers={"Authorization": f"Bearer {seller_token}"},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "awaiting_payment" in detail
    assert "shipped" in detail


@pytest.mark.asyncio
async def test_seller_update_status_wrong_seller_404(
    client: AsyncClient, seller_order_setup
):
    """A seller with no items in the order cannot update its status (→ 404)."""
    from tests.conftest import create_user_token_helper

    other_token = await create_user_token_helper(client, "seller")
    setup = seller_order_setup

    resp = await client.patch(
        f"/api/v1/seller/orders/{setup['order_id']}/status",
        json={"status": "processing"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_seller_endpoints_require_seller_role(
    client: AsyncClient, seller_order_setup, buyer_token: str
):
    """Buyer attempting seller endpoints → 403."""
    setup = seller_order_setup
    headers = {"Authorization": f"Bearer {buyer_token}"}

    r1 = await client.get("/api/v1/seller/orders", headers=headers)
    assert r1.status_code == 403

    r2 = await client.get(f"/api/v1/seller/orders/{setup['order_id']}", headers=headers)
    assert r2.status_code == 403

    r3 = await client.patch(
        f"/api/v1/seller/orders/{setup['order_id']}/status",
        json={"status": "processing"},
        headers=headers,
    )
    assert r3.status_code == 403


# ===========================================================================
# Buyer history / detail / cancel tests
# ===========================================================================

@pytest.fixture
async def buyer_order_setup(client: AsyncClient, buyer_token: str, seller_token: str, db_session):
    """
    Creates a category + product (seller-owned) and places one order as the
    buyer.  Returns a dict with useful IDs and a pre-flushed product ref.
    """
    res = await db_session.execute(select(User).where(User.role == "seller"))
    seller = res.scalars().first()

    category = Category(slug="buyer-test-cat", display_name="Buyer Cat", description="desc")
    db_session.add(category)
    await db_session.flush()

    product = Product(
        seller_id=seller.id,
        category_id=category.id,
        title="Clay Pot",
        description="Hand-crafted",
        price_paise=2500,
        stock=10,
        is_active=True,
    )
    db_session.add(product)
    await db_session.flush()

    resp = await client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": str(product.id), "quantity": 2}],
            "shipping_address": "456 Market Road, Pune",
        },
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert resp.status_code == 201
    order_data = resp.json()

    return {
        "product": product,
        "order_id": order_data["id"],
        "buyer_token": buyer_token,
        "seller_token": seller_token,
    }


@pytest.mark.asyncio
async def test_buyer_list_orders_happy_path(
    client: AsyncClient, buyer_order_setup, buyer_token: str
):
    """Buyer sees their own orders in the history list."""
    setup = buyer_order_setup
    resp = await client.get(
        "/api/v1/orders",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert data["page"] == 1
    order_ids = [o["id"] for o in data["items"]]
    assert setup["order_id"] in order_ids


@pytest.mark.asyncio
async def test_buyer_get_order_happy_path(
    client: AsyncClient, buyer_order_setup, buyer_token: str
):
    """Buyer can fetch the full detail of their order."""
    setup = buyer_order_setup
    resp = await client.get(
        f"/api/v1/orders/{setup['order_id']}",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == setup["order_id"]
    assert len(data["items"]) == 1
    assert data["items"][0]["quantity"] == 2


@pytest.mark.asyncio
async def test_buyer_get_order_another_buyers_order_403(
    client: AsyncClient, buyer_order_setup
):
    """A different buyer accessing someone else's order gets 403."""
    from tests.conftest import create_user_token_helper

    other_buyer_token = await create_user_token_helper(client, "buyer")
    setup = buyer_order_setup

    resp = await client.get(
        f"/api/v1/orders/{setup['order_id']}",
        headers={"Authorization": f"Bearer {other_buyer_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_buyer_cancel_awaiting_payment_restores_stock(
    client: AsyncClient, buyer_order_setup, buyer_token: str, db_session
):
    """Cancelling while awaiting_payment sets status=cancelled and restores stock."""
    setup = buyer_order_setup
    product = setup["product"]

    # Confirm stock was decremented by the order (qty=2, original=10 → 8)
    await db_session.refresh(product)
    assert product.stock == 8

    resp = await client.post(
        f"/api/v1/orders/{setup['order_id']}/cancel",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "cancelled"

    # Stock should be back to 10
    await db_session.refresh(product)
    assert product.stock == 10

    # Audit log emitted
    audit_res = await db_session.execute(
        select(AuditLog).where(AuditLog.event_type == "order.cancelled")
    )
    audit = audit_res.scalar_one_or_none()
    assert audit is not None
    assert audit.details["order_id"] == setup["order_id"]


@pytest.mark.asyncio
async def test_buyer_cancel_while_processing_422(
    client: AsyncClient, buyer_order_setup, buyer_token: str, seller_token: str
):
    """Cancelling an order that is already in 'processing' returns 422."""
    setup = buyer_order_setup

    # Seller advances to processing first
    await client.patch(
        f"/api/v1/seller/orders/{setup['order_id']}/status",
        json={"status": "processing"},
        headers={"Authorization": f"Bearer {seller_token}"},
    )

    resp = await client.post(
        f"/api/v1/orders/{setup['order_id']}/cancel",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert resp.status_code == 422
    assert "processing" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_buyer_double_cancel_422(
    client: AsyncClient, buyer_order_setup, buyer_token: str
):
    """Attempting to cancel an already-cancelled order returns 422."""
    setup = buyer_order_setup

    # First cancel — should succeed
    r1 = await client.post(
        f"/api/v1/orders/{setup['order_id']}/cancel",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert r1.status_code == 200

    # Second cancel — should fail
    r2 = await client.post(
        f"/api/v1/orders/{setup['order_id']}/cancel",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert r2.status_code == 422
    assert "cancelled" in r2.json()["detail"]
