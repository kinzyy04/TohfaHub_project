import uuid
from datetime import datetime
from pydantic import BaseModel, Field

class ProductCreate(BaseModel):
    title: str = Field(..., max_length=120)
    description: str = Field(..., max_length=2000)
    price_paise: int = Field(..., ge=100, le=1_000_000)
    stock: int = Field(default=1, ge=0)
    category_id: uuid.UUID
    image_urls: list[str] = Field(default_factory=list)

class ProductUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    price_paise: int | None = Field(default=None, ge=100, le=1_000_000)
    stock: int | None = Field(default=None, ge=0)
    category_id: uuid.UUID | None = None
    image_urls: list[str] | None = None
    is_active: bool | None = None

class ProductRead(BaseModel):
    id: uuid.UUID
    seller_id: uuid.UUID
    category_id: uuid.UUID
    title: str
    description: str
    price_paise: int
    stock: int
    image_urls: list[str]
    is_active: bool
    is_sponsored: bool
    created_at: datetime
    updated_at: datetime
    shop_name: str | None = None

    class Config:
        from_attributes = True
