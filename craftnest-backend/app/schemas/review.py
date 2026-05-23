import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class ReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    body: str | None = Field(None, max_length=500)


class ReviewRead(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    buyer_id: uuid.UUID
    order_id: uuid.UUID
    rating: int
    body: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewListRead(BaseModel):
    """Paginated list of reviews for a product."""
    items: list[ReviewRead]
    total: int
    page: int
    page_size: int
