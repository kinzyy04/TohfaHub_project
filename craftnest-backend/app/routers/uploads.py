import os
import uuid
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException, status, Request, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from PIL import Image
from app.core.database import get_db
from app.models.user import User
from app.routers.deps import RoleChecker
from app.core.rate_limit import rate_limit_by_user
from app.utils.request_meta import extract_request_meta
from app.services.audit_service import log_event

router = APIRouter(prefix="/api/v1/uploads", tags=["Uploads"])

@router.post("/product-image", status_code=status.HTTP_200_OK)
@rate_limit_by_user("20/hour")
async def upload_product_image(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["seller"])),
):
    # 1. Allowed content types: image/jpeg, image/png, image/webp ONLY
    if file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported media type. Only JPEG, PNG, and WebP are allowed."
        )

    # 2. Max size: 5 MB
    max_size = 5 * 1024 * 1024
    size = 0
    contents = b""
    
    try:
        while True:
            chunk = await file.read(1024 * 1024) # Read in 1MB chunks
            if not chunk:
                break
            size += len(chunk)
            contents += chunk
            if size > max_size:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="File size exceeds the 5 MB limit."
                )
    finally:
        await file.close()

    # 3. Sniff bytes with Pillow to confirm it really is an image
    try:
        img_temp = Image.open(BytesIO(contents))
        img_temp.verify()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Invalid image format or corrupted file."
        )

    # 4. Open again for actual processing (since verify() invalidates the image object)
    try:
        image = Image.open(BytesIO(contents))
        image.load()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Invalid image data."
        )

    # 5. Re-encode to JPEG, resize keeping aspect ratio (max dim 1600px), strip EXIF
    # Convert RGBA/P to RGB for JPEG compatibility
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        background = Image.new("RGB", image.size, (255, 255, 255))
        # Use split()[3] if RGBA for transparency masking
        mask = image.split()[3] if image.mode == "RGBA" else None
        background.paste(image, mask=mask)
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")

    width, height = image.size
    max_dim = 1600
    if width > max_dim or height > max_dim:
        if width > height:
            new_width = max_dim
            new_height = int(height * (max_dim / width))
        else:
            new_height = max_dim
            new_width = int(width * (max_dim / height))
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # 6. Save to /media/products/<uuid>.jpg
    media_dir = os.path.join("media", "products")
    os.makedirs(media_dir, exist_ok=True)
    filename = f"{uuid.uuid4()}.jpg"
    filepath = os.path.join(media_dir, filename)
    image.save(filepath, "JPEG", quality=85)

    # 7. Audit log upload event
    ip_address, user_agent = extract_request_meta(request)
    await log_event(
        db=db,
        event_type="upload.product_image",
        user_id=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        details={"size_bytes": size, "content_type": file.content_type}
    )
    # The get_db generator automatically commits/flushes on return.

    return {"url": f"/media/products/{filename}"}
