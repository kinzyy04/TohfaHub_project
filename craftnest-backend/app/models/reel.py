import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.core.database import Base, GUID

class Reel(Base):
    __tablename__ = "reels"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("products.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    video_url: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    thumbnail_url: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    duration_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    caption: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )
    view_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    like_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    comment_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    seller = relationship("User")
    product = relationship("Product")


class ReelLike(Base):
    __tablename__ = "reel_likes"

    reel_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("reels.id", ondelete="CASCADE"),
        primary_key=True,
    )
    buyer_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    reel = relationship("Reel")
    buyer = relationship("User")


class ReelSave(Base):
    __tablename__ = "reel_saves"

    reel_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("reels.id", ondelete="CASCADE"),
        primary_key=True,
    )
    buyer_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    reel = relationship("Reel")
    buyer = relationship("User")


class ReelComment(Base):
    __tablename__ = "reel_comments"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    reel_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("reels.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    body: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    reel = relationship("Reel")
    author = relationship("User")


class ReelView(Base):
    __tablename__ = "reel_views"

    reel_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("reels.id", ondelete="CASCADE"),
        primary_key=True,
    )
    ip_address: Mapped[str] = mapped_column(
        String,
        primary_key=True,
    )
    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    reel = relationship("Reel")
