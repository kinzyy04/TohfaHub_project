import pytest
from io import BytesIO
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.future import select
from app.models.audit_log import AuditLog

@pytest.fixture
async def seller_headers(seller_token: str) -> dict:
    return {"Authorization": f"Bearer {seller_token}"}

@pytest.fixture
async def buyer_headers(buyer_token: str) -> dict:
    return {"Authorization": f"Bearer {buyer_token}"}

# ==========================================
# POST /api/v1/uploads/product-image
# ==========================================

@pytest.mark.asyncio
async def test_upload_image_success(client: AsyncClient, seller_headers: dict, db):
    # Create a small valid PNG in memory
    img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    files = {"file": ("test.png", png_bytes, "image/png")}
    response = await client.post(
        "/api/v1/uploads/product-image",
        files=files,
        headers=seller_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "url" in data
    assert data["url"].startswith("/media/products/")
    assert data["url"].endswith(".jpg")

    # Verify audit log exists
    audit_res = await db.execute(
        select(AuditLog).where(AuditLog.event_type == "upload.product_image")
    )
    audit_log = audit_res.scalar_one_or_none()
    assert audit_log is not None
    assert audit_log.details.get("content_type") == "image/png"
    assert audit_log.details.get("size_bytes") == len(png_bytes)

    # Let's verify we can download it as public
    get_res = await client.get(data["url"])
    assert get_res.status_code == 200
    # Confirm it is indeed a valid JPEG image by opening it
    downloaded_img = Image.open(BytesIO(get_res.content))
    assert downloaded_img.format == "JPEG"

@pytest.mark.asyncio
async def test_upload_image_too_large(client: AsyncClient, seller_headers: dict):
    # 6 MB of dummy bytes with PNG header to pass content type / header sniffing if checked first
    large_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * (6 * 1024 * 1024)
    files = {"file": ("large.png", large_bytes, "image/png")}
    response = await client.post(
        "/api/v1/uploads/product-image",
        files=files,
        headers=seller_headers
    )
    assert response.status_code == 413

@pytest.mark.asyncio
async def test_upload_fake_image_payload_sniffing(client: AsyncClient, seller_headers: dict):
    # Plain text file content but claiming to be PNG
    fake_png_bytes = b"This is just some plain text, not a PNG image."
    files = {"file": ("fake.png", fake_png_bytes, "image/png")}
    response = await client.post(
        "/api/v1/uploads/product-image",
        files=files,
        headers=seller_headers
    )
    assert response.status_code == 415

@pytest.mark.asyncio
async def test_upload_invalid_mime_type(client: AsyncClient, seller_headers: dict):
    # Valid PNG bytes but claiming to be text/plain
    img = Image.new("RGBA", (10, 10), (0, 255, 0, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    files = {"file": ("test.txt", png_bytes, "text/plain")}
    response = await client.post(
        "/api/v1/uploads/product-image",
        files=files,
        headers=seller_headers
    )
    assert response.status_code == 415

@pytest.mark.asyncio
async def test_upload_buyer_forbidden(client: AsyncClient, buyer_headers: dict):
    img = Image.new("RGBA", (10, 10), (0, 0, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    files = {"file": ("test.png", png_bytes, "image/png")}
    response = await client.post(
        "/api/v1/uploads/product-image",
        files=files,
        headers=buyer_headers
    )
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_media_path_traversal_protection(client: AsyncClient):
    # Try to access GET /media/../app/core/config.py
    # Test normalized path (should either be blocked or return 404)
    response = await client.get("/media/../app/core/config.py")
    assert response.status_code in [404, 403]

    # Test encoded dot-dot-slash path
    response_encoded = await client.get("/media/%2e%2e/app/core/config.py")
    assert response_encoded.status_code in [404, 403]
