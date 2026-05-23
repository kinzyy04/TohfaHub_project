import uuid
from datetime import datetime
from sqlalchemy import Integer, Text, DateTime, ForeignKey, CheckConstraint, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.core.database import Base, GUID


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("products.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    buyer_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("orders.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    product = relationship("Product", backref="reviews")
    buyer = relationship("User")
    order = relationship("Order")

    __table_args__ = (
        CheckConstraint("rating IN (1,2,3,4,5)", name="ck_review_rating"),
        UniqueConstraint("product_id", "buyer_id", name="uq_review_product_buyer"),
    )
