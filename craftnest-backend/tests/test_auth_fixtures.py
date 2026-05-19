import pytest
from jose import jwt
from app.core.config import settings

@pytest.mark.asyncio
async def test_auth_fixtures(buyer_token, seller_token, admin_token):
    # Verify we get non-empty strings
    assert buyer_token and isinstance(buyer_token, str)
    assert seller_token and isinstance(seller_token, str)
    assert admin_token and isinstance(admin_token, str)

    # Decode tokens and check subject
    payload_buyer = jwt.decode(buyer_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    payload_seller = jwt.decode(seller_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    payload_admin = jwt.decode(admin_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

    assert payload_buyer["sub"].startswith("buyer_")
    assert payload_seller["sub"].startswith("seller_")
    assert payload_admin["sub"].startswith("admin_")
