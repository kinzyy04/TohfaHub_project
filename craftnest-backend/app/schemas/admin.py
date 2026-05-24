import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class BanRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)

class AdminSellerListItem(BaseModel):
    user_id: uuid.UUID
    email: str
    shop_name: str | None = None
    is_active: bool
    product_count: int
    order_count: int
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)

class AdminProductRead(BaseModel):
    id: uuid.UUID
    title: str
    price_paise: int
    stock: int
    is_active: bool
    avg_rating: float | None = None
    review_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class AdminOrderItemRead(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    seller_id: uuid.UUID
    title_snapshot: str
    price_snapshot_paise: int
    quantity: int

    model_config = ConfigDict(from_attributes=True)

class AdminOrderRead(BaseModel):
    id: uuid.UUID
    buyer_id: uuid.UUID
    status: str
    total_paise: int
    shipping_address: str
    created_at: datetime
    items: list[AdminOrderItemRead]

    model_config = ConfigDict(from_attributes=True)

class AdminSellerProfileRead(BaseModel):
    shop_name: str | None = None
    bio: str | None = None
    shipping_days: int
    instagram_handle: str | None = None
    payout_method: str | None = None

    model_config = ConfigDict(from_attributes=True)

class AdminUserRead(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None = None
    role: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class AdminSellerDetailResponse(BaseModel):
    user: AdminUserRead
    seller_profile: AdminSellerProfileRead | None = None
    products: list[AdminProductRead]
    recent_orders: list[AdminOrderRead]

    model_config = ConfigDict(from_attributes=True)


class AdminOrderListRow(BaseModel):
    id: uuid.UUID
    buyer_id: uuid.UUID
    buyer_email: str
    status: str
    total_paise: int
    shipping_address: str
    seller_note: str | None = None
    tracking_code: str | None = None
    created_at: datetime
    updated_at: datetime
    seller_shop_name: str
    items: list[AdminOrderItemRead]

    model_config = ConfigDict(from_attributes=True)


class AdminOrderListRead(BaseModel):
    items: list[AdminOrderListRow]
    total: int
    page: int
    page_size: int


class AdminOrderStatusOverrideRequest(BaseModel):
    status: str = Field(..., min_length=1)
    admin_note: str | None = Field(None, max_length=500)


class RefundFlagRequest(BaseModel):
    note: str = Field(..., min_length=1, max_length=500)


class AdminCategoryResponse(BaseModel):
    id: uuid.UUID
    slug: str
    display_name: str
    description: str
    icon_emoji: str | None = None
    sort_order: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class CategoryCreateRequest(BaseModel):
    slug: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., max_length=500)
    icon_emoji: str | None = Field(None, max_length=20)
    sort_order: int = Field(0)


class CategoryUpdateRequest(BaseModel):
    slug: str | None = Field(None, min_length=1, max_length=100)
    display_name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    icon_emoji: str | None = Field(None, max_length=20)
    sort_order: int | None = Field(None)


class ProductSponsoredToggleRequest(BaseModel):
    is_sponsored: bool

