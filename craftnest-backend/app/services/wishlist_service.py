import uuid
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from app.models.wishlist import Wishlist
from app.models.product import Product
from app.models.user import User
from app.services.audit_service import log_event

async def add_to_wishlist(
    db: AsyncSession,
    buyer_id: uuid.UUID,
    product_id: uuid.UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    # Verify product exists and is active
    res = await db.execute(
        select(Product).where(Product.id == product_id, Product.is_active == True)
    )
    product = res.scalar_one_or_none()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Check if already wishlisted
    stmt = select(Wishlist).where(
        Wishlist.buyer_id == buyer_id,
        Wishlist.product_id == product_id
    )
    res_w = await db.execute(stmt)
    wishlist_item = res_w.scalar_one_or_none()

    if not wishlist_item:
        wishlist_item = Wishlist(buyer_id=buyer_id, product_id=product_id)
        db.add(wishlist_item)
        await db.flush()

        # Log audit event
        await log_event(
            db=db,
            event_type="wishlist.added",
            user_id=buyer_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"product_id": str(product_id)}
        )
        await db.flush()

async def remove_from_wishlist(
    db: AsyncSession,
    buyer_id: uuid.UUID,
    product_id: uuid.UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    stmt = select(Wishlist).where(
        Wishlist.buyer_id == buyer_id,
        Wishlist.product_id == product_id
    )
    res = await db.execute(stmt)
    wishlist_item = res.scalar_one_or_none()
    if not wishlist_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not in wishlist"
        )

    await db.delete(wishlist_item)
    await db.flush()

    # Log audit event
    await log_event(
        db=db,
        event_type="wishlist.removed",
        user_id=buyer_id,
        ip_address=ip_address,
        user_agent=user_agent,
        details={"product_id": str(product_id)}
    )
    await db.flush()

async def get_wishlist(
    db: AsyncSession,
    buyer_id: uuid.UUID,
) -> list[Product]:
    # Select products wishlisted by this buyer, joined loading category and seller profiles
    stmt = (
        select(Product)
        .join(Wishlist, Product.id == Wishlist.product_id)
        .where(Wishlist.buyer_id == buyer_id, Product.is_active == True)
        .options(
            joinedload(Product.category),
            joinedload(Product.seller).joinedload(User.seller_profile)
        )
        .order_by(Wishlist.created_at.desc())
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())
