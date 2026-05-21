import uuid
from datetime import datetime
import sqlalchemy as sa
from sqlalchemy import String, ForeignKey, DateTime, Integer
from sqlalchemy import String, ForeignKey, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base, GUID

class BuyerProfile(Base):
    __tablename__ = "buyer_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True
    )
    default_address: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False
    )

    user = relationship("User", back_populates="buyer_profile")


class SellerProfile(Base):
    __tablename__ = "seller_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True
    )
    shop_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    bio: Mapped[str | None] = mapped_column(String(500), nullable=True)
    shipping_days: Mapped[int] = mapped_column(Integer, default=5, server_default=sa.text("5"), nullable=False)
    instagram_handle: Mapped[str | None] = mapped_column(String(30), nullable=True)
    payout_method: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False
    )

    user = relationship("User", back_populates="seller_profile")
