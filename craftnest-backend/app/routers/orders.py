import uuid
from fastapi import APIRouter, Depends, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.routers.deps import RoleChecker
from app.core.rate_limit import rate_limit_by_user
from app.utils.request_meta import extract_request_meta
from app.schemas.order import OrderCreate, OrderRead, OrderStatusUpdate, OrderListRead
from app.services import order_service

router = APIRouter(prefix="/api/v1", tags=["Orders"])


# ---------------------------------------------------------------------------
# Buyer endpoints
# ---------------------------------------------------------------------------

@router.post("/orders", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
@rate_limit_by_user("10/minute")
async def create_order(
    request: Request,
    order_in: OrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["buyer"])),
):
    ip_address, user_agent = extract_request_meta(request)
    return await order_service.create_order(
        db=db,
        buyer_id=current_user.id,
        order_in=order_in,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@router.get(
    "/orders",
    response_model=OrderListRead,
    summary="Buyer's order history",
)
async def list_buyer_orders(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["buyer"])),
):
    """
    Returns all orders placed by the authenticated buyer, sorted newest-first.
    """
    return await order_service.list_buyer_orders(
        db=db,
        buyer_id=current_user.id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/orders/{order_id}",
    response_model=OrderRead,
    summary="Get one order (buyer must own it)",
)
async def get_buyer_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["buyer"])),
):
    """
    Returns the requested order. Returns **403** if the order belongs to
    a different buyer.
    """
    return await order_service.get_buyer_order(
        db=db,
        order_id=order_id,
        buyer_id=current_user.id,
    )


@router.post(
    "/orders/{order_id}/cancel",
    response_model=OrderRead,
    summary="Cancel an order",
)
async def cancel_order(
    request: Request,
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["buyer"])),
):
    """
    Cancels the order and restores product stock. Only allowed when status is
    `awaiting_payment` or `paid_offline`. Returns **422** otherwise.
    """
    ip_address, user_agent = extract_request_meta(request)
    return await order_service.cancel_order(
        db=db,
        order_id=order_id,
        buyer_id=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )


# ---------------------------------------------------------------------------
# Seller endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/seller/orders",
    response_model=OrderListRead,
    summary="List orders containing the seller's products",
)
async def list_seller_orders(
    request: Request,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: str | None = Query(None, description="Filter by order status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["seller"])),
):
    """
    Returns all orders that contain at least one item belonging to the
    authenticated seller. Items from other sellers in the same order are
    **not** included in the response. Sorted by `created_at` DESC.
    """
    result = await order_service.list_seller_orders(
        db=db,
        seller_id=current_user.id,
        page=page,
        page_size=page_size,
        status_filter=status,
    )
    return result


@router.get(
    "/seller/orders/{order_id}",
    response_model=OrderRead,
    summary="Get a single order (seller's items only)",
)
async def get_seller_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["seller"])),
):
    """
    Returns the requested order with only the authenticated seller's items.
    Returns 404 if the order doesn't exist or the seller has no items in it.
    """
    return await order_service.get_seller_order(
        db=db,
        order_id=order_id,
        seller_id=current_user.id,
    )


@router.patch(
    "/seller/orders/{order_id}/status",
    response_model=OrderRead,
    summary="Advance an order's status",
)
async def update_order_status(
    request: Request,
    order_id: uuid.UUID,
    update_in: OrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["seller"])),
):
    """
    Advances the order status according to the seller state machine:

    - `awaiting_payment` → `processing`
    - `paid_offline`     → `processing`
    - `processing`       → `shipped`   *(tracking_code required)*
    - `shipped`          → `delivered`

    Returns 422 for invalid transitions or missing `tracking_code`.
    Returns 404 if the seller has no items in this order.
    """
    ip_address, user_agent = extract_request_meta(request)
    return await order_service.update_order_status(
        db=db,
        order_id=order_id,
        seller_id=current_user.id,
        update_in=update_in,
        ip_address=ip_address,
        user_agent=user_agent,
    )
