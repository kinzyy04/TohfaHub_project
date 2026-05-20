import uuid
from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.user import User
from app.routers.deps import RoleChecker
from app.core.rate_limit import rate_limit_by_user
from app.utils.request_meta import extract_request_meta
from app.schemas.browse import ProductBrowseResponse
from app.services import wishlist_service

router = APIRouter(prefix="/api/v1/wishlist", tags=["Wishlist"])

@router.post("/{product_id}", status_code=status.HTTP_200_OK)
@rate_limit_by_user("120/minute")
async def add_to_wishlist(
    request: Request,
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["buyer"])),
):
    ip_address, user_agent = extract_request_meta(request)
    await wishlist_service.add_to_wishlist(
        db=db,
        buyer_id=current_user.id,
        product_id=product_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return {"message": "Product added to wishlist"}

@router.delete("/{product_id}", status_code=status.HTTP_200_OK)
@rate_limit_by_user("120/minute")
async def remove_from_wishlist(
    request: Request,
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["buyer"])),
):
    ip_address, user_agent = extract_request_meta(request)
    await wishlist_service.remove_from_wishlist(
        db=db,
        buyer_id=current_user.id,
        product_id=product_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return {"message": "Product removed from wishlist"}

@router.get("", response_model=list[ProductBrowseResponse])
@rate_limit_by_user("120/minute")
async def get_wishlist(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["buyer"])),
):
    return await wishlist_service.get_wishlist(
        db=db,
        buyer_id=current_user.id,
    )
