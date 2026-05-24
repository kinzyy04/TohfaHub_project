import uuid
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text, func
from sqlalchemy.orm import selectinload

from app.models.product import Product
from app.models.order import Order, OrderItem
from app.schemas.order import OrderCreate, OrderStatusUpdate
from app.services.audit_service import log_event
from app.services.notification_service import create_notification

# ---------------------------------------------------------------------------
# Seller state-machine definition
# ---------------------------------------------------------------------------
# Maps each current status to the set of statuses a seller is allowed to
# transition to.  Transitions outside this map are rejected with 422.
SELLER_TRANSITIONS: dict[str, set[str]] = {
    "awaiting_payment": {"processing"},
    "paid_offline":     {"processing"},
    "processing":       {"shipped"},
    "shipped":          {"delivered"},
}

# Transitions that mandate a tracking_code in the request body
REQUIRES_TRACKING: set[str] = {"shipped"}


# ---------------------------------------------------------------------------
# Buyer-facing: create order
# ---------------------------------------------------------------------------

async def create_order(
    db: AsyncSession,
    buyer_id: uuid.UUID,
    order_in: OrderCreate,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Order:
    # 1. Combine item quantities by product_id
    item_map = {}
    for item in order_in.items:
        item_map[item.product_id] = item_map.get(item.product_id, 0) + item.quantity

    # 2. Fetch products and verify active status & stock
    products_map = {}
    for pid, qty in item_map.items():
        result = await db.execute(select(Product).where(Product.id == pid))
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Product {pid} not found"
            )
        if not product.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Product {pid} is inactive"
            )
        if product.stock < qty:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Insufficient stock for product {pid}"
            )
        products_map[pid] = product

    # 3. All DB updates must be inside one transaction
    try:
        async with db.begin_nested():
            # Atomic stock decrement
            for pid, qty in item_map.items():
                update_stmt = text(
                    "UPDATE products SET stock = stock - :qty WHERE id = :pid AND stock >= :qty RETURNING id"
                )
                result = await db.execute(
                    update_stmt,
                    {"qty": qty, "pid": str(pid)}
                )
                row = result.fetchone()
                if not row:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="insufficient stock"
                    )

            # 4. Compute total_paise
            total_paise = 0
            order_items = []
            for item in order_in.items:
                product = products_map[item.product_id]
                price_snapshot_paise = product.price_paise
                total_paise += price_snapshot_paise * item.quantity

                order_items.append(
                    OrderItem(
                        product_id=product.id,
                        seller_id=product.seller_id,
                        title_snapshot=product.title,
                        price_snapshot_paise=price_snapshot_paise,
                        quantity=item.quantity
                    )
                )

            # 5. Set status = 'awaiting_payment' and insert order
            order = Order(
                buyer_id=buyer_id,
                status="awaiting_payment",
                total_paise=total_paise,
                shipping_address=order_in.shipping_address,
            )
            db.add(order)
            await db.flush()

            # 6. Insert order items
            for oi in order_items:
                oi.order_id = order.id
                db.add(oi)
            await db.flush()

            # 7. Audit-log: event_type='order.created', target_id=order.id
            await log_event(
                db=db,
                event_type="order.created",
                user_id=buyer_id,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"target_id": str(order.id)}
            )
            await db.flush()

            # 8. Notify each unique seller that has items in this order
            seen_sellers: set[uuid.UUID] = set()
            for oi in order_items:
                if oi.seller_id not in seen_sellers:
                    seen_sellers.add(oi.seller_id)
                    await create_notification(
                        db=db,
                        user_id=oi.seller_id,
                        type="order.received",
                        title="New order!",
                        body=f"Someone just ordered your {oi.title_snapshot}.",
                        related_id=order.id,
                    )
            await db.flush()

        # Load order with items loaded eagerly
        query = (
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.id == order.id)
        )
        res = await db.execute(query)
        full_order = res.scalar_one()
        return full_order

    except Exception as e:
        raise e


# ---------------------------------------------------------------------------
# Seller-facing helpers
# ---------------------------------------------------------------------------

async def _load_order_for_seller(
    db: AsyncSession,
    order_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> Order:
    """
    Load an Order only if it contains at least one item belonging to seller_id.
    Returns the Order ORM object with ALL items loaded (caller filters if needed).
    Raises 404 if the order doesn't exist or the seller has no items in it.
    """
    # Check that this seller has at least one item in the order
    exists_q = (
        select(OrderItem.order_id)
        .where(
            OrderItem.order_id == order_id,
            OrderItem.seller_id == seller_id,
        )
        .limit(1)
    )
    result = await db.execute(exists_q)
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order_q = (
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id)
    )
    res = await db.execute(order_q)
    order = res.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


def _filter_items_for_seller(order: Order, seller_id: uuid.UUID) -> Order:
    """
    Mutates the in-memory order.items list to only those belonging to seller_id.
    Returns the same order object for chaining.
    """
    order.items = [i for i in order.items if i.seller_id == seller_id]
    return order


# ---------------------------------------------------------------------------
# Seller-facing: list orders
# ---------------------------------------------------------------------------

async def list_seller_orders(
    db: AsyncSession,
    seller_id: uuid.UUID,
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[str] = None,
) -> dict:
    """
    Return a paginated list of orders that contain at least one item from
    this seller, optionally filtered by order status.
    Each returned order only exposes the seller's own items.
    """
    # Sub-query: distinct order IDs that include this seller's items
    seller_order_ids_q = (
        select(OrderItem.order_id)
        .where(OrderItem.seller_id == seller_id)
        .distinct()
        .subquery()
    )

    base_q = select(Order).where(Order.id.in_(select(seller_order_ids_q)))
    if status_filter:
        base_q = base_q.where(Order.status == status_filter)

    # Total count
    count_q = select(func.count()).select_from(base_q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # Paginated fetch, sorted newest-first
    orders_q = (
        base_q
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(orders_q)
    orders = list(result.scalars().all())

    # Filter items per order to only this seller's items
    for order in orders:
        _filter_items_for_seller(order, seller_id)

    return {
        "items": orders,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------------
# Seller-facing: get single order
# ---------------------------------------------------------------------------

async def get_seller_order(
    db: AsyncSession,
    order_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> Order:
    """
    Fetch one order scoped to the seller's own items.
    Raises 404 if the seller has no items in this order.
    """
    order = await _load_order_for_seller(db, order_id, seller_id)
    return _filter_items_for_seller(order, seller_id)


# ---------------------------------------------------------------------------
# Seller-facing: advance order status
# ---------------------------------------------------------------------------

async def update_order_status(
    db: AsyncSession,
    order_id: uuid.UUID,
    seller_id: uuid.UUID,
    update_in: OrderStatusUpdate,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Order:
    """
    Advance an order's status according to the seller state machine.

    Raises:
        404 – order not found / seller has no items in it.
        422 – transition not allowed from current status.
        422 – tracking_code missing when transitioning to 'shipped'.
    """
    order = await _load_order_for_seller(db, order_id, seller_id)

    allowed = SELLER_TRANSITIONS.get(order.status)
    if allowed is None or update_in.status not in allowed:
        allowed_str = ", ".join(sorted(allowed)) if allowed else "none"
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Cannot transition from '{order.status}' to '{update_in.status}'. "
                f"Allowed transition(s) from '{order.status}': {allowed_str}."
            ),
        )

    if update_in.status in REQUIRES_TRACKING and not update_in.tracking_code:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="tracking_code is required when transitioning to 'shipped'.",
        )

    old_status = order.status

    async with db.begin_nested():
        order.status = update_in.status
        if update_in.seller_note is not None:
            order.seller_note = update_in.seller_note
        if update_in.tracking_code is not None:
            order.tracking_code = update_in.tracking_code
        db.add(order)
        await db.flush()

        await log_event(
            db=db,
            event_type="order.status_changed",
            user_id=seller_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "from": old_status,
                "to": update_in.status,
                "tracking_code": order.tracking_code,
            },
        )
        await db.flush()

        # Notify buyer on shipped / delivered
        if update_in.status == "shipped":
            await create_notification(
                db=db,
                user_id=order.buyer_id,
                type="order.shipped",
                title="Your order is on the way",
                body=f"Tracking: {order.tracking_code}.",
                related_id=order.id,
            )
            await db.flush()
        elif update_in.status == "delivered":
            await create_notification(
                db=db,
                user_id=order.buyer_id,
                type="order.delivered",
                title="Order delivered!",
                body="Leave a review to help others.",
                related_id=order.id,
            )
            await db.flush()

    # Reload with items for return value
    await db.refresh(order)
    return _filter_items_for_seller(order, seller_id)


# ---------------------------------------------------------------------------
# Buyer-facing: list order history
# ---------------------------------------------------------------------------

# Statuses from which a buyer may cancel
BUYER_CANCELLABLE: set[str] = {"awaiting_payment", "paid_offline"}


async def list_buyer_orders(
    db: AsyncSession,
    buyer_id: uuid.UUID,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """
    Return a paginated list of all orders placed by this buyer,
    sorted newest-first with items eagerly loaded.
    """
    base_q = select(Order).where(Order.buyer_id == buyer_id)

    count_q = select(func.count()).select_from(base_q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    orders_q = (
        base_q
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(orders_q)
    orders = list(result.scalars().all())

    return {
        "items": orders,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------------
# Buyer-facing: get single order (ownership check)
# ---------------------------------------------------------------------------

async def get_buyer_order(
    db: AsyncSession,
    order_id: uuid.UUID,
    buyer_id: uuid.UUID,
) -> Order:
    """
    Fetch one order. Returns 403 if the order exists but belongs to a
    different buyer (to avoid leaking order existence to other users).
    """
    order_q = (
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id)
    )
    res = await db.execute(order_q)
    order = res.scalar_one_or_none()

    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.buyer_id != buyer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your order")

    return order


# ---------------------------------------------------------------------------
# Buyer-facing: cancel order
# ---------------------------------------------------------------------------

async def cancel_order(
    db: AsyncSession,
    order_id: uuid.UUID,
    buyer_id: uuid.UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Order:
    """
    Cancel an order that is still in a cancellable status.

    Raises:
        404 – order not found.
        403 – order belongs to a different buyer.
        422 – order is not in a cancellable status (awaiting_payment / paid_offline).

    On success:
        - Sets status = 'cancelled'.
        - Restores stock for every order item atomically within one savepoint.
        - Emits audit log: event_type='order.cancelled'.
    """
    # Ownership + existence check
    order = await get_buyer_order(db, order_id, buyer_id)

    if order.status not in BUYER_CANCELLABLE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Order cannot be cancelled in its current status '{order.status}'. "
                f"Cancellation is only allowed when status is: "
                f"{', '.join(sorted(BUYER_CANCELLABLE))}."
            ),
        )

    async with db.begin_nested():
        # Restore stock for every item
        for item in order.items:
            restore_stmt = text(
                "UPDATE products SET stock = stock + :qty WHERE id = :pid"
            )
            await db.execute(restore_stmt, {"qty": item.quantity, "pid": str(item.product_id)})

        # Mark cancelled
        order.status = "cancelled"
        db.add(order)
        await db.flush()

        await log_event(
            db=db,
            event_type="order.cancelled",
            user_id=buyer_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"order_id": str(order_id)},
        )
        await db.flush()

    await db.refresh(order)
    return order
