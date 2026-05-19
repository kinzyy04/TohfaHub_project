import uuid
from pydantic import BaseModel, EmailStr, ConfigDict

class UserBase(BaseModel):
    email: EmailStr
    role: str = "buyer"

class UserCreate(UserBase):
    password: str
    full_name: str | None = None

class UserResponse(UserBase):
    id: uuid.UUID
    full_name: str | None = None
    is_active: bool
    
    model_config = ConfigDict(from_attributes=True)
