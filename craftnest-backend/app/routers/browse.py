from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.rate_limit import rate_limit_by_user
from app.schemas.browse import CategoryBrowseResponse, ProductBrowseResponse, HomeBrowseResponse
from app.services import browse_service

router = APIRouter(prefix="/api/v1/browse", tags=["Browse"])

@router.get("/categories", response_model=list[CategoryBrowseResponse])
@rate_limit_by_user("60/minute")
async def get_categories(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    return await browse_service.get_all_categories(db=db)

@router.get("/home", response_model=HomeBrowseResponse)
@rate_limit_by_user("60/minute")
async def get_home(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    return await browse_service.get_home_products(db=db)

@router.get("/category/{slug}", response_model=list[ProductBrowseResponse])
@rate_limit_by_user("60/minute")
async def get_category_products(
    request: Request,
    slug: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return await browse_service.get_products_by_category(
        db=db,
        category_slug=slug,
        limit=limit,
        offset=offset,
    )

@router.get("/search", response_model=list[ProductBrowseResponse])
@rate_limit_by_user("60/minute")
async def search(
    request: Request,
    q: str = Query(..., min_length=2, max_length=50),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return await browse_service.search_products(
        db=db,
        q=q,
        limit=limit,
        offset=offset,
    )
