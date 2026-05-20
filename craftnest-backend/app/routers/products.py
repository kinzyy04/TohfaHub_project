from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.user import User
from app.routers.deps import RoleChecker
from app.core.rate_limit import rate_limit_by_user
from app.utils.request_meta import extract_request_meta
from app.schemas.product import ProductCreate, ProductUpdate, ProductRead
from app.services import product_service

router = APIRouter(prefix="/api/v1/products", tags=["Products"])

@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
@rate_limit_by_user("120/minute")
async def create_product(
    request: Request,
    product_in: ProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["seller"])),
):
    ip_address, user_agent = extract_request_meta(request)
    return await product_service.create_product(
        db=db,
        seller_id=current_user.id,
        product_in=product_in,
        ip_address=ip_address,
        user_agent=user_agent,
    )

@router.get("/mine", response_model=list[ProductRead])
@rate_limit_by_user("120/minute")
async def list_my_products(
    request: Request,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["seller"])),
):
    return await product_service.get_seller_products(
        db=db,
        seller_id=current_user.id,
        limit=limit,
        offset=offset,
    )

@router.get("/{id}", response_model=ProductRead)
@rate_limit_by_user("120/minute")
async def get_product(
    request: Request,
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    return await product_service.get_product_by_id(db=db, product_id=id)

@router.patch("/{id}", response_model=ProductRead)
@rate_limit_by_user("120/minute")
async def update_product(
    request: Request,
    id: uuid.UUID,
    product_in: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["seller"])),
):
    ip_address, user_agent = extract_request_meta(request)
    return await product_service.update_product(
        db=db,
        product_id=id,
        seller_id=current_user.id,
        product_in=product_in,
        ip_address=ip_address,
        user_agent=user_agent,
    )

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
@rate_limit_by_user("120/minute")
async def delete_product(
    request: Request,
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["seller"])),
):
    ip_address, user_agent = extract_request_meta(request)
    await product_service.delete_product(
        db=db,
        product_id=id,
        seller_id=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
