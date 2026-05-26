import sys
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, Boolean, Text, text, Numeric, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym
from sqlalchemy.sql import func
from app.core.database import Base, GUID

# Ensure app.models is imported so that the old registry is populated first
import app.models

# Safely deregister old SellerProfile to avoid duplicates on the same table name
if "SellerProfile" in Base.registry._class_registry:
    del Base.registry._class_registry["SellerProfile"]
if "seller_profiles" in Base.metadata.tables:
    Base.metadata.remove(Base.metadata.tables["seller_profiles"])

class SellerProfile(Base):
    __tablename__ = "seller_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    store_name: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=False,
        default=lambda: f"Store_{uuid.uuid4().hex[:8]}",
    )
    store_handle: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=False,
        default=lambda: f"store-{uuid.uuid4().hex[:8]}",
    )
    bio: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    location: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )
    website_url: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )
    artisan_story: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    avatar_url: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )
    is_accepting_orders: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False,
    )
    is_online: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    shipping_days: Mapped[int] = mapped_column(
        Integer,
        default=5,
        server_default=text("5"),
        nullable=False,
    )
    payout_method: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )
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

    @property
    def _shop_name_prop(self) -> str | None:
        if self.store_name and self.store_name.startswith("Store_"):
            return None
        return self.store_name

    @_shop_name_prop.setter
    def _shop_name_prop(self, value: str | None):
        self.store_name = value

    @property
    def _instagram_handle_prop(self) -> str | None:
        if self.store_handle and self.store_handle.startswith("store-"):
            return None
        return self.store_handle

    @_instagram_handle_prop.setter
    def _instagram_handle_prop(self, value: str | None):
        self.store_handle = value

    # Synonyms for legacy support
    shop_name = synonym("store_name", descriptor=property(_shop_name_prop.fget, _shop_name_prop.fset))
    instagram_handle = synonym("store_handle", descriptor=property(_instagram_handle_prop.fget, _instagram_handle_prop.fset))

    # Relationships
    user = relationship("User", back_populates="seller_profile")
    onboarding_status = relationship(
        "SellerOnboardingStatus",
        back_populates="seller",
        cascade="all, delete-orphan",
    )
    payout_details = relationship(
        "SellerPayoutDetails",
        uselist=False,
        back_populates="seller",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<SellerProfile id={self.id} store_name={self.store_name} store_handle={self.store_handle}>"


class SellerOnboardingStatus(Base):
    __tablename__ = "seller_onboarding_status"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("seller_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_key: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    is_complete: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    seller = relationship("SellerProfile", back_populates="onboarding_status")

    def __repr__(self) -> str:
        return f"<SellerOnboardingStatus id={self.id} seller_id={self.seller_id} step_key={self.step_key} is_complete={self.is_complete}>"


class SellerPayoutDetails(Base):
    __tablename__ = "seller_payout_details"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("seller_profiles.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    masked_account: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )
    payout_method: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    pending_payout_amount: Mapped[float] = mapped_column(
        Numeric(10, 2),
        default=0.0,
        server_default=text("0.00"),
        nullable=False,
    )
    payout_schedule: Mapped[str] = mapped_column(
        String,
        default="Every Monday 10 AM",
        server_default=text("'Every Monday 10 AM'"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    seller = relationship("SellerProfile", back_populates="payout_details")

    def __repr__(self) -> str:
        return f"<SellerPayoutDetails id={self.id} seller_id={self.seller_id} payout_method={self.payout_method} pending_payout_amount={self.pending_payout_amount}>"


# Override references in sys.modules to point to the new classes
if "app.models" in sys.modules:
    sys.modules["app.models"].SellerProfile = SellerProfile
    sys.modules["app.models"].SellerOnboardingStatus = SellerOnboardingStatus
    sys.modules["app.models"].SellerPayoutDetails = SellerPayoutDetails
if "app.models.profile" in sys.modules:
    sys.modules["app.models.profile"].SellerProfile = SellerProfile
