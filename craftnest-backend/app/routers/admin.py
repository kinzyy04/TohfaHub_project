import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import require_admin
from app.models.user import User
from app.utils.request_meta import extract_request_meta
from app.services.audit_service import log_event
from app.services import admin_service
from app.core.rate_limit import rate_limit_by_user
from app.schemas.admin import (
    AdminSellerListItem, AdminSellerDetailResponse, BanRequest,
    AdminOrderListRead, AdminOrderStatusOverrideRequest, RefundFlagRequest,
    AdminCategoryResponse, CategoryCreateRequest, CategoryUpdateRequest,
    ProductSponsoredToggleRequest
)
from app.schemas.user import UserResponse
from app.schemas.product import ProductRead

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])

@router.get("/stats")
@rate_limit_by_user("60/minute")
async def get_admin_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    # Audit log: event_type='admin.stats.viewed'
    ip_address, user_agent = extract_request_meta(request)
    await log_event(
        db=db,
        event_type="admin.stats.viewed",
        user_id=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.flush()
    
    return await admin_service.get_admin_stats(db)


@router.get("/sellers", response_model=list[AdminSellerListItem])
@rate_limit_by_user("60/minute")
async def get_sellers(
    request: Request,
    search: str | None = Query(None, description="Search by shop_name or email"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return await admin_service.list_sellers(
        db=db,
        search=search,
        is_active=is_active,
        page=page,
        limit=limit
    )


@router.get("/sellers/{user_id}", response_model=AdminSellerDetailResponse)
@rate_limit_by_user("60/minute")
async def get_seller(
    request: Request,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return await admin_service.get_seller_details(db=db, user_id=user_id)


@router.post("/sellers/{user_id}/ban", response_model=UserResponse)
@rate_limit_by_user("60/minute")
async def ban_seller(
    request: Request,
    user_id: uuid.UUID,
    payload: BanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    ip_address, user_agent = extract_request_meta(request)
    return await admin_service.ban_seller(
        db=db,
        user_id=user_id,
        reason=payload.reason,
        admin_id=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent
    )


@router.post("/sellers/{user_id}/unban", response_model=UserResponse)
@rate_limit_by_user("60/minute")
async def unban_seller(
    request: Request,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    ip_address, user_agent = extract_request_meta(request)
    return await admin_service.unban_seller(
        db=db,
        user_id=user_id,
        admin_id=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent
    )


# ---------------------------------------------------------------------------
# Goal A — Admin order oversight
# ---------------------------------------------------------------------------

@router.get("/orders", response_model=AdminOrderListRead)
@rate_limit_by_user("60/minute")
async def list_admin_orders(
    request: Request,
    status: str | None = Query(None, description="Filter by status"),
    buyer_email: str | None = Query(None, description="Filter by buyer email"),
    seller_id: uuid.UUID | None = Query(None, description="Filter by seller ID"),
    date_from: datetime | None = Query(None, description="Filter from date (inclusive)"),
    date_to: datetime | None = Query(None, description="Filter to date (inclusive)"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return await admin_service.list_orders(
        db=db,
        status=status,
        buyer_email=buyer_email,
        seller_id=seller_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        limit=limit
    )


@router.patch("/orders/{id}/status")
@rate_limit_by_user("60/minute")
async def force_order_status(
    request: Request,
    id: uuid.UUID,
    payload: AdminOrderStatusOverrideRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    ip_address, user_agent = extract_request_meta(request)
    return await admin_service.force_order_status(
        db=db,
        order_id=id,
        new_status=payload.status,
        admin_note=payload.admin_note,
        admin_id=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent
    )


@router.post("/orders/{id}/refund_flag")
@rate_limit_by_user("60/minute")
async def flag_order_refund(
    request: Request,
    id: uuid.UUID,
    payload: RefundFlagRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    ip_address, user_agent = extract_request_meta(request)
    return await admin_service.flag_order_refund(
        db=db,
        order_id=id,
        note=payload.note,
        admin_id=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent
    )


# ---------------------------------------------------------------------------
# Goal B — Category management
# ---------------------------------------------------------------------------

@router.get("/categories", response_model=list[AdminCategoryResponse])
@rate_limit_by_user("60/minute")
async def list_admin_categories(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return await admin_service.list_all_categories(db=db)


@router.post("/categories", response_model=AdminCategoryResponse, status_code=status.HTTP_201_CREATED)
@rate_limit_by_user("60/minute")
async def create_category(
    request: Request,
    payload: CategoryCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    ip_address, user_agent = extract_request_meta(request)
    return await admin_service.create_category(
        db=db,
        slug=payload.slug,
        display_name=payload.display_name,
        description=payload.description,
        icon_emoji=payload.icon_emoji,
        sort_order=payload.sort_order,
        admin_id=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent
    )


@router.patch("/categories/{id}", response_model=AdminCategoryResponse)
@rate_limit_by_user("60/minute")
async def update_category(
    request: Request,
    id: uuid.UUID,
    payload: CategoryUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    ip_address, user_agent = extract_request_meta(request)
    return await admin_service.update_category(
        db=db,
        category_id=id,
        slug=payload.slug,
        display_name=payload.display_name,
        description=payload.description,
        icon_emoji=payload.icon_emoji,
        sort_order=payload.sort_order,
        admin_id=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent
    )


@router.delete("/categories/{id}", status_code=status.HTTP_200_OK)
@rate_limit_by_user("60/minute")
async def delete_category(
    request: Request,
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    ip_address, user_agent = extract_request_meta(request)
    return await admin_service.delete_category(
        db=db,
        category_id=id,
        admin_id=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent
    )


# ---------------------------------------------------------------------------
# Goal C — Toggle sponsored status
# ---------------------------------------------------------------------------

@router.patch("/products/{id}/sponsored", response_model=ProductRead)
@rate_limit_by_user("60/minute")
async def toggle_product_sponsored(
    request: Request,
    id: uuid.UUID,
    payload: ProductSponsoredToggleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    ip_address, user_agent = extract_request_meta(request)
    return await admin_service.toggle_product_sponsored(
        db=db,
        product_id=id,
        is_sponsored=payload.is_sponsored,
        admin_id=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent
    )

