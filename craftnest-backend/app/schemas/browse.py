import uuid
from pydantic import BaseModel, Field, model_validator

class CategoryBrowseResponse(BaseModel):
    id: uuid.UUID
    slug: str
    display_name: str
    description: str
    icon_emoji: str | None
    sort_order: int

    class Config:
        from_attributes = True

class ProductBrowseResponse(BaseModel):
    id: uuid.UUID
    title: str
    price_paise: int
    image_urls: list[str]
    shop_name: str | None
    shipping_days: int
    category_slug: str

    class Config:
        from_attributes = True

    @model_validator(mode="before")
    @classmethod
    def resolve_nested_fields(cls, data):
        # Handles both SQLAlchemy models and raw dictionaries
        if not isinstance(data, dict):
            seller = getattr(data, "seller", None)
            seller_profile = getattr(seller, "seller_profile", None) if seller else None
            category = getattr(data, "category", None)
            
            return {
                "id": data.id,
                "title": data.title,
                "price_paise": data.price_paise,
                "image_urls": data.image_urls,
                "shop_name": getattr(seller_profile, "shop_name", None) if seller_profile else None,
                "shipping_days": getattr(seller_profile, "shipping_days", 5) if seller_profile else 5,
                "category_slug": getattr(category, "slug", "") if category else ""
            }
        return data

class HomeBrowseResponse(BaseModel):
    sponsored: list[ProductBrowseResponse]
    recent: list[ProductBrowseResponse]
    next_cursor: str | None = None
