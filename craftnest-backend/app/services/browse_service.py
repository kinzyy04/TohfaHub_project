import uuid
from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from app.models.category import Category
from app.models.product import Product
from app.models.user import User

async def get_all_categories(db: AsyncSession) -> list[Category]:
    result = await db.execute(
        select(Category).order_by(Category.sort_order.asc())
    )
    return list(result.scalars().all())

async def get_home_products(db: AsyncSession) -> dict:
    # 1. Fetch up to 3 random sponsored products
    sponsored_stmt = (
        select(Product)
        .options(
            joinedload(Product.category),
            joinedload(Product.seller).joinedload(User.seller_profile)
        )
        .where(Product.is_active == True, Product.is_sponsored == True)
        .order_by(func.random())
        .limit(3)
    )
    sponsored_res = await db.execute(sponsored_stmt)
    sponsored_products = list(sponsored_res.scalars().all())

    # 2. Fetch latest 20 active products
    recent_stmt = (
        select(Product)
        .options(
            joinedload(Product.category),
            joinedload(Product.seller).joinedload(User.seller_profile)
        )
        .where(Product.is_active == True)
        .order_by(Product.created_at.desc())
        .limit(20)
    )
    recent_res = await db.execute(recent_stmt)
    recent_products = list(recent_res.scalars().all())

    return {
        "sponsored": sponsored_products,
        "recent": recent_products
    }

async def get_products_by_category(
    db: AsyncSession,
    category_slug: str,
    limit: int = 20,
    offset: int = 0,
) -> list[Product]:
    # Check if category exists
    cat_check = await db.execute(
        select(Category).where(Category.slug == category_slug)
    )
    if not cat_check.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )

    stmt = (
        select(Product)
        .options(
            joinedload(Product.category),
            joinedload(Product.seller).joinedload(User.seller_profile)
        )
        .join(Category, Product.category_id == Category.id)
        .where(Product.is_active == True, Category.slug == category_slug)
        .order_by(Product.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())

async def search_products(
    db: AsyncSession,
    q: str,
    limit: int = 20,
    offset: int = 0,
) -> list[Product]:
    stmt = (
        select(Product)
        .options(
            joinedload(Product.category),
            joinedload(Product.seller).joinedload(User.seller_profile)
        )
        .where(
            Product.is_active == True,
            or_(
                Product.title.ilike(f"%{q}%"),
                Product.description.ilike(f"%{q}%")
            )
        )
        .order_by(Product.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
