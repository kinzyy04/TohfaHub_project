# ---------------------------------------------------------------------------
# Order State Machine
# ---------------------------------------------------------------------------
#
#   pending
#     │
#     ▼
#   awaiting_payment
#     │            ╲
#     ▼              ▼
#   paid_offline    cancelled   (buyer cancels before processing)
#     │
#     ▼
#   processing
#     │         ╲
#     ▼           ▼
#   shipped      cancelled   (admin / seller cancels with reason)
#     │
#     ▼
#   delivered
#     │
#     ▼
#   refunded   (Week 8, via Razorpay)
#
# ---------------------------------------------------------------------------

import uuid
from datetime import datetime
from sqlalchemy import (
    String, Integer, Text, DateTime, ForeignKey,
    CheckConstraint, text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base, GUID


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    buyer_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'pending'"),
    )
    total_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    shipping_address: Mapped[str] = mapped_column(Text, nullable=False)
    seller_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    tracking_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )
    buyer = relationship("User", backref="orders")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','awaiting_payment','paid_offline',"
            "'processing','shipped','delivered','cancelled','refunded')",
            name="ck_order_status",
        ),
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("orders.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("products.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    price_snapshot_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default=text("1"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    order: Mapped[Order] = relationship("Order", back_populates="items")
    product = relationship("Product")
    seller = relationship("User")

    __table_args__ = (
        CheckConstraint(
            "quantity >= 1",
            name="ck_order_item_quantity",
        ),
    )
