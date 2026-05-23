import uuid
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text, func

from app.models.review import Review
from app.models.order import Order, OrderItem
from app.schemas.review import ReviewCreate
from app.services.audit_service import log_event


async def create_review(
    db: AsyncSession,
    product_id: uuid.UUID,
    buyer_id: uuid.UUID,
    review_in: ReviewCreate,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Review:
    """
    Create a review for a product.

    Guards:
        - Buyer must have a delivered order containing the product.
        - Buyer must not have already reviewed this product.
    On success:
        - Inserts the review.
        - Atomically updates products.avg_rating and products.review_count.
        - Emits audit log: 'review.created'.
    """
    # 1. Check that a delivered order for this buyer+product exists
    delivered_item_q = (
        select(OrderItem.order_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            OrderItem.product_id == product_id,
            Order.buyer_id == buyer_id,
            Order.status == "delivered",
        )
        .limit(1)
    )
    result = await db.execute(delivered_item_q)
    qualifying_order_id = result.scalar_one_or_none()

    if qualifying_order_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "You can only review a product after it has been delivered. "
                "No delivered order found for this product."
            ),
        )

    # 2. Check buyer hasn't already reviewed this product
    existing_q = select(Review.id).where(
        Review.product_id == product_id,
        Review.buyer_id == buyer_id,
    ).limit(1)
    existing = (await db.execute(existing_q)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="You have already reviewed this product.",
        )

    async with db.begin_nested():
        # 3. Insert the review
        review = Review(
            product_id=product_id,
            buyer_id=buyer_id,
            order_id=qualifying_order_id,
            rating=review_in.rating,
            body=review_in.body,
        )
        db.add(review)
        await db.flush()

        # 4. Atomically update avg_rating and review_count
        update_stmt = text(
            """
            UPDATE products
            SET
                review_count = review_count + 1,
                avg_rating   = CASE
                    WHEN avg_rating IS NULL THEN :new_rating
                    ELSE (avg_rating * review_count + :new_rating) / (review_count + 1)
                END
            WHERE id = :pid
            """
        )
        await db.execute(
            update_stmt,
            {"new_rating": float(review_in.rating), "pid": str(product_id)},
        )

        # 5. Audit log
        await log_event(
            db=db,
            event_type="review.created",
            user_id=buyer_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "review_id": str(review.id),
                "product_id": str(product_id),
                "rating": review_in.rating,
            },
        )
        await db.flush()

    return review


async def list_product_reviews(
    db: AsyncSession,
    product_id: uuid.UUID,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """
    Return a paginated list of reviews for a product, newest-first.
    """
    base_q = select(Review).where(Review.product_id == product_id)

    count_q = select(func.count()).select_from(base_q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    reviews_q = (
        base_q
        .order_by(Review.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(reviews_q)
    reviews = list(result.scalars().all())

    return {
        "items": reviews,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
