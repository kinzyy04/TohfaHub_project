import uuid
import re
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

class BecomeSellerRequest(BaseModel):
    store_name: str = Field(..., min_length=3, max_length=60)
    store_handle: str = Field(..., min_length=3, max_length=30)
    bio: str | None = None

    @field_validator("store_handle")
    @classmethod
    def validate_store_handle(cls, v: str) -> str:
        # lowercase alphanumeric + hyphens only
        if not re.match(r"^[a-z0-9\-]+$", v):
            raise ValueError("Store handle must contain only lowercase alphanumeric characters and hyphens")
        return v

class OnboardingStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    step_key: str
    is_complete: bool

class BecomeSellerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    seller_id: uuid.UUID
    store_name: str
    store_handle: str
    onboarding_steps: list[OnboardingStepResponse]

    @model_validator(mode="before")
    @classmethod
    def populate_fields(cls, data):
        if not isinstance(data, dict):
            # Map ORM model attributes manually
            # Sort the onboarding steps by step_key or as they are stored
            steps = [
                OnboardingStepResponse(step_key=s.step_key, is_complete=s.is_complete)
                for s in sorted(data.onboarding_status or [], key=lambda x: x.step_key)
            ]
            return {
                "seller_id": data.id,
                "store_name": data.store_name,
                "store_handle": data.store_handle,
                "onboarding_steps": steps
            }
        return data

class OnboardingProgress(BaseModel):
    complete: int
    total: int

class SellerStudioShellResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    store_name: str
    store_handle: str
    avatar_url: str | None
    is_accepting_orders: bool
    pending_payout_amount: float
    payout_schedule: str
    onboarding_progress: OnboardingProgress


from datetime import datetime

class SellerStudioProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    store_name: str
    store_handle: str
    bio: str | None = None
    location: str | None = None
    website_url: str | None = None
    artisan_story: str | None = None
    avatar_url: str | None = None
    is_accepting_orders: bool
    is_online: bool
    created_at: datetime


class SellerProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    store_name: str | None = Field(default=None, min_length=3, max_length=60)
    bio: str | None = None
    location: str | None = None
    website_url: str | None = None
    artisan_story: str | None = None
    avatar_url: str | None = None
    store_handle: str | None = None


class ToggleOrdersResponse(BaseModel):
    is_accepting_orders: bool
    message: str


class PayoutDetailsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    masked_account: str | None = None
    payout_method: str | None = None
    
    @field_validator("payout_method")
    @classmethod
    def validate_payout_method(cls, v: str | None) -> str | None:
        if v is not None and v not in ("UPI", "bank"):
            raise ValueError("payout_method must be either 'UPI' or 'bank'")
        return v


class PayoutDetailsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    masked_account: str | None = None
    payout_method: str
    pending_payout_amount: float
    payout_schedule: str
