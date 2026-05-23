import uuid
from fastapi import APIRouter, Depends, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.routers.deps import RoleChecker
from app.utils.request_meta import extract_request_meta
from app.schemas.review import ReviewCreate, ReviewRead, ReviewListRead
from app.services import review_service

router = APIRouter(prefix="/api/v1/products", tags=["Reviews"])


@router.post(
    "/{product_id}/reviews",
    response_model=ReviewRead,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a review for a product",
)
async def create_review(
    request: Request,
    product_id: uuid.UUID,
    review_in: ReviewCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["buyer"])),
):
    """
    Submit a review (rating 1–5, optional body ≤500 chars) for a product.

    Requirements:
    - Caller must be a **buyer** (403 otherwise).
    - Buyer must have a **delivered** order containing this product (422 otherwise).
    - Buyer must not have already reviewed this product (422 otherwise).
    """
    ip_address, user_agent = extract_request_meta(request)
    return await review_service.create_review(
        db=db,
        product_id=product_id,
        buyer_id=current_user.id,
        review_in=review_in,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@router.get(
    "/{product_id}/reviews",
    response_model=ReviewListRead,
    summary="List reviews for a product",
)
async def list_product_reviews(
    product_id: uuid.UUID,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
):
    """
    Public endpoint — returns paginated reviews for the given product,
    sorted newest-first.
    """
    return await review_service.list_product_reviews(
        db=db,
        product_id=product_id,
        page=page,
        page_size=page_size,
    )
