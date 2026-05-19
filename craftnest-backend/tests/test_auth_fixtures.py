import pytest
import uuid
from jose import jwt
from app.core.config import settings

@pytest.mark.asyncio
async def test_auth_fixtures(buyer_token, seller_token, admin_token):
    # Verify we get non-empty strings
    assert buyer_token and isinstance(buyer_token, str)
    assert seller_token and isinstance(seller_token, str)
    assert admin_token and isinstance(admin_token, str)

    # Decode tokens using JWT_SECRET
    payload_buyer = jwt.decode(buyer_token, settings.JWT_SECRET, algorithms=[settings.ALGORITHM])
    payload_seller = jwt.decode(seller_token, settings.JWT_SECRET, algorithms=[settings.ALGORITHM])
    payload_admin = jwt.decode(admin_token, settings.JWT_SECRET, algorithms=[settings.ALGORITHM])

    # Verify sub is a valid UUID
    assert uuid.UUID(payload_buyer["sub"])
    assert uuid.UUID(payload_seller["sub"])
    assert uuid.UUID(payload_admin["sub"])

    # Verify roles are stored properly in claims
    assert payload_buyer["role"] == "buyer"
    assert payload_seller["role"] == "seller"
    assert payload_admin["role"] == "admin"
