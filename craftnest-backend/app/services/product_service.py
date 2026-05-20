import uuid
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.product import Product
from app.models.category import Category
from app.models.user import User
from app.models.profile import SellerProfile
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.audit_service import log_event

async def create_product(
    db: AsyncSession,
    seller_id: uuid.UUID,
    product_in: ProductCreate,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Product:
    # Verify category exists
    cat_result = await db.execute(
        select(Category).where(Category.id == product_in.category_id)
    )
    if not cat_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category not found"
        )

    product = Product(
        seller_id=seller_id,
        category_id=product_in.category_id,
        title=product_in.title,
        description=product_in.description,
        price_paise=product_in.price_paise,
        stock=product_in.stock,
        image_urls=product_in.image_urls,
    )
    db.add(product)
    await db.flush()

    # Log audit event
    await log_event(
        db=db,
        event_type="product.created",
        user_id=seller_id,
        ip_address=ip_address,
        user_agent=user_agent,
        details={"target_id": str(product.id)}
    )
    await db.flush()
    await db.refresh(product)

    # Populate shop_name for returned schema
    sp_result = await db.execute(
        select(SellerProfile.shop_name).where(SellerProfile.user_id == seller_id)
    )
    product.shop_name = sp_result.scalar_one_or_none()

    return product

async def get_seller_products(
    db: AsyncSession,
    seller_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
) -> list[Product]:
    query = (
        select(Product, SellerProfile.shop_name)
        .join(User, Product.seller_id == User.id)
        .outerjoin(SellerProfile, User.id == SellerProfile.user_id)
        .where(Product.seller_id == seller_id)
        .order_by(Product.created_at.desc(), Product.title.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    products = []
    for p, sn in result.all():
        p.shop_name = sn
        products.append(p)
    return products

async def get_product_by_id(db: AsyncSession, product_id: uuid.UUID) -> Product:
    query = (
        select(Product, SellerProfile.shop_name)
        .join(User, Product.seller_id == User.id)
        .outerjoin(SellerProfile, User.id == SellerProfile.user_id)
        .where(Product.id == product_id, Product.is_active == True)
    )
    result = await db.execute(query)
    row = result.first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    product, shop_name = row
    product.shop_name = shop_name
    return product

async def update_product(
    db: AsyncSession,
    product_id: uuid.UUID,
    seller_id: uuid.UUID,
    product_in: ProductUpdate,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Product:
    # Must retrieve active product
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.is_active == True)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Must own product (otherwise return 404 to hide its existence)
    if product.seller_id != seller_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Verify category if changing
    if product_in.category_id is not None:
        cat_result = await db.execute(
            select(Category).where(Category.id == product_in.category_id)
        )
        if not cat_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category not found"
            )

    # Apply update values
    update_data = product_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)
    await db.flush()

    # Log audit event
    await log_event(
        db=db,
        event_type="product.updated",
        user_id=seller_id,
        ip_address=ip_address,
        user_agent=user_agent,
        details={"target_id": str(product.id)}
    )
    await db.flush()
    await db.refresh(product)

    # Populate shop_name
    sp_result = await db.execute(
        select(SellerProfile.shop_name).where(SellerProfile.user_id == seller_id)
    )
    product.shop_name = sp_result.scalar_one_or_none()

    return product

async def delete_product(
    db: AsyncSession,
    product_id: uuid.UUID,
    seller_id: uuid.UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    # Must retrieve active product
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.is_active == True)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Must own product
    if product.seller_id != seller_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Soft delete
    product.is_active = False
    await db.flush()

    # Log audit event
    await log_event(
        db=db,
        event_type="product.deleted",
        user_id=seller_id,
        ip_address=ip_address,
        user_agent=user_agent,
        details={"target_id": str(product.id)}
    )
    await db.flush()
