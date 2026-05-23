import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

class OrderItemCreate(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(..., ge=1)

class OrderCreate(BaseModel):
    items: list[OrderItemCreate] = Field(..., min_length=1)
    shipping_address: str = Field(..., min_length=1)

class OrderItemRead(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    product_id: uuid.UUID
    seller_id: uuid.UUID
    title_snapshot: str
    price_snapshot_paise: int
    quantity: int
    created_at: datetime

    class Config:
        from_attributes = True

class OrderRead(BaseModel):
    id: uuid.UUID
    buyer_id: uuid.UUID
    status: str
    total_paise: int
    shipping_address: str
    seller_note: str | None = None
    tracking_code: str | None = None
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemRead]

    class Config:
        from_attributes = True

# ---- Seller-facing schemas ----

class OrderStatusUpdate(BaseModel):
    status: Literal["processing", "shipped", "delivered"]
    seller_note: str | None = None
    tracking_code: str | None = None

class OrderListRead(BaseModel):
    """Paginated list of orders (seller view – items filtered to seller's own)."""
    items: list[OrderRead]
    total: int
    page: int
    page_size: int
