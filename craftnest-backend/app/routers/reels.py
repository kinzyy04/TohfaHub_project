import os
import uuid
import base64
import shutil
import tempfile
import subprocess
from datetime import datetime
from PIL import Image

from fastapi import APIRouter, Depends, HTTPException, status, Request, File, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_, and_, update, case, literal
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.user import User
from app.models.product import Product
from app.models.reel import Reel, ReelLike, ReelSave, ReelComment, ReelView
from app.models.follow import Follow
from app.models.audit_log import AuditLog
from app.routers.deps import RoleChecker
from app.core.rate_limit import rate_limit_by_user, get_client_ip, limiter
from app.schemas.reel import ReelRead, ReelFeedResponse, ReelFeedItem, ProductSummary, SellerSummary, ReelCommentCreate, ReelCommentRead, ReelCommentsResponse
from app.core.security import decode_access_token
from app.core.deps import oauth2_scheme, get_current_user
from datetime import timezone, timedelta

router = APIRouter(prefix="/api/v1/reels", tags=["Reels"])

# Dynamically add winget packages path to environment PATH if not already in PATH
if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
    winget_packages_root = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    if os.path.exists(winget_packages_root):
        for root, dirs, files in os.walk(winget_packages_root):
            if "ffmpeg.exe" in files and "ffprobe.exe" in files:
                os.environ["PATH"] = root + os.pathsep + os.environ["PATH"]
                break

def check_ffmpeg_installed() -> bool:
    """Check if ffmpeg and ffprobe are available in the system PATH."""
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


async def get_optional_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User | None:
    """Dependency to optionally retrieve the authenticated user.
    If the token is invalid or missing, it returns None instead of raising 401.
    """
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        user_id_str = payload.get("sub")
        if not user_id_str:
            return None
        user_id = uuid.UUID(user_id_str)
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user and user.is_active:
            return user
    except Exception:
        pass
    return None

def decode_cursor(cursor_str: str) -> tuple[int, datetime, uuid.UUID]:
    """Decodes the base64 feed pagination cursor."""
    try:
        decoded_bytes = base64.b64decode(cursor_str.encode())
        decoded_str = decoded_bytes.decode()
        parts = decoded_str.split("|")
        if len(parts) == 3:
            return int(parts[0]), datetime.fromisoformat(parts[1]), uuid.UUID(parts[2])
        else:
            # Fallback for old cursors
            return 1, datetime.fromisoformat(parts[0]), uuid.UUID(parts[1])
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cursor format"
        )

def encode_cursor(is_followed: int, created_at: datetime, item_id: uuid.UUID) -> str:
    """Encodes the sort tie-breakers into a base64 pagination cursor."""
    cursor_str = f"{is_followed}|{created_at.isoformat()}|{item_id}"
    return base64.b64encode(cursor_str.encode()).decode()

@router.post("/upload", response_model=ReelRead, status_code=status.HTTP_201_CREATED)
@rate_limit_by_user("10/hour")
async def upload_reel(
    request: Request,
    file: UploadFile = File(...),
    product_id: uuid.UUID = Form(...),
    caption: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["seller"])),
):
    # 1. Allowed MIME types: video/mp4, video/quicktime, video/webm
    allowed_types = ["video/mp4", "video/quicktime", "video/webm"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported media type. Only MP4, QuickTime, and WebM videos are allowed."
        )

    # 2. Check if product exists and belongs to the authenticated seller
    prod_res = await db.execute(select(Product).where(Product.id == product_id))
    product = prod_res.scalar_one_or_none()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    if product.seller_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own the product associated with this reel."
        )

    # 3. Stream file and cap size at 30 MB
    max_size = 30 * 1024 * 1024
    size = 0
    contents = b""
    try:
        while True:
            chunk = await file.read(4 * 1024 * 1024) # Read in 4MB chunks
            if not chunk:
                break
            size += len(chunk)
            contents += chunk
            if size > max_size:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="File size exceeds the 30 MB limit."
                )
    finally:
        await file.close()

    # 4. Check if ffmpeg/ffprobe are installed
    if not check_ffmpeg_installed():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="FFmpeg/FFprobe is not installed or not in the system PATH."
        )

    # 5. Save input video to a temp file for ffmpeg processing
    suffix = os.path.splitext(file.filename or "")[1] or ".mp4"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_in:
        temp_in.write(contents)
        temp_in_path = temp_in.name

    # Prepare output paths
    reel_id = uuid.uuid4()
    media_reels_dir = os.path.join("media", "reels")
    os.makedirs(media_reels_dir, exist_ok=True)
    out_video_filename = f"{reel_id}.mp4"
    out_thumb_filename = f"{reel_id}.jpg"
    out_video_path = os.path.join(media_reels_dir, out_video_filename)
    out_thumb_path = os.path.join(media_reels_dir, out_thumb_filename)

    try:
        # 6. Read duration using ffprobe
        ffprobe_cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            temp_in_path
        ]
        try:
            proc = subprocess.run(
                ffprobe_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            duration = float(proc.stdout.strip())
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to read video metadata: {str(e)}"
            )

        # Reject if > 60 seconds (422)
        if duration > 60.0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Video duration is {duration:.2f} seconds, which exceeds the maximum limit of 60 seconds."
            )

        # 7. Re-encode to MP4 H.264 720p at 1500 kbps, strip metadata
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-i", temp_in_path,
            "-vf", "scale=-2:720",
            "-c:v", "libx264",
            "-b:v", "1500k",
            "-maxrate", "1500k",
            "-bufsize", "3000k",
            "-map_metadata", "-1",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            out_video_path
        ]
        try:
            subprocess.run(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
        except subprocess.CalledProcessError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Video re-encoding failed: {e.stderr.decode() if e.stderr else str(e)}"
            )

        # 8. Generate thumbnail JPG at 1-second mark (or 0.0 / midpoint if video is shorter)
        thumb_time = 1.0 if duration >= 1.0 else 0.0
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_thumb:
            temp_thumb_path = temp_thumb.name

        try:
            ffmpeg_thumb_cmd = [
                "ffmpeg",
                "-y",
                "-ss", str(thumb_time),
                "-i", out_video_path,
                "-vframes", "1",
                temp_thumb_path
            ]
            subprocess.run(
                ffmpeg_thumb_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
            # Re-save with quality 80 via PIL
            with Image.open(temp_thumb_path) as img:
                img.save(out_thumb_path, "JPEG", quality=80)
        finally:
            if os.path.exists(temp_thumb_path):
                os.remove(temp_thumb_path)

    finally:
        # Clean up input temporary file
        if os.path.exists(temp_in_path):
            os.remove(temp_in_path)

    # 9. Insert into database
    new_reel = Reel(
        id=reel_id,
        seller_id=current_user.id,
        product_id=product_id,
        video_url=f"/media/reels/{out_video_filename}",
        thumbnail_url=f"/media/reels/{out_thumb_filename}",
        duration_seconds=int(round(duration)),
        caption=caption,
        view_count=0,
        like_count=0,
        comment_count=0,
        is_active=True
    )
    db.add(new_reel)
    await db.flush()

    return new_reel

@router.delete("/{id}", status_code=status.HTTP_200_OK)
async def delete_reel(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["seller"])),
):
    result = await db.execute(select(Reel).where(Reel.id == id))
    reel = result.scalar_one_or_none()
    if not reel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reel not found"
        )
    if reel.seller_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this reel"
        )
    reel.is_active = False
    await db.flush()
    return {"detail": "Reel deleted successfully"}


@router.get("/feed", response_model=ReelFeedResponse)
@limiter.limit("60/minute", key_func=get_client_ip)
async def get_reels_feed(
    request: Request,
    limit: int = 10,
    cursor: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    # Enforce a maximum limit cap to protect resources
    limit = min(max(1, limit), 50)

    # Query only active reels of active sellers whose products are still active
    query = (
        select(Reel)
        .join(Product, Reel.product_id == Product.id)
        .join(User, Reel.seller_id == User.id)
        .where(
            Reel.is_active == True,
            Product.is_active == True,
            User.is_active == True
        )
    )

    is_followed_expr = literal(1)
    if current_user:
        followed_subq = select(Follow.followed_id).where(Follow.follower_id == current_user.id)
        is_followed_expr = case(
            (Reel.seller_id.in_(followed_subq), 0),
            else_=1
        )

    # Keyset pagination logic
    if cursor:
        cursor_is_followed, cursor_created_at, cursor_id = decode_cursor(cursor)
        query = query.where(
            or_(
                is_followed_expr > cursor_is_followed,
                and_(
                    is_followed_expr == cursor_is_followed,
                    Reel.created_at < cursor_created_at
                ),
                and_(
                    is_followed_expr == cursor_is_followed,
                    Reel.created_at == cursor_created_at,
                    Reel.id < cursor_id
                )
            )
        )

    # Sort by followed status, then newest first
    query = query.order_by(is_followed_expr.asc(), Reel.created_at.desc(), Reel.id.desc())
    
    # Fetch limit + 1 items to check if there is a next page
    query = query.limit(limit + 1)
    
    # Eagerly load product and seller (with seller_profile)
    query = query.options(
        selectinload(Reel.product),
        selectinload(Reel.seller).selectinload(User.seller_profile)
    )

    result = await db.execute(query)
    reels = result.scalars().all()

    has_next = len(reels) > limit
    items = reels[:limit]

    # Compute followed sellers for cursor encoding and response
    followed_sellers = set()
    if current_user and items:
        seller_ids = [r.seller_id for r in items]
        followed_res = await db.execute(
            select(Follow.followed_id).where(
                Follow.follower_id == current_user.id,
                Follow.followed_id.in_(seller_ids)
            )
        )
        followed_sellers = set(followed_res.scalars().all())

    next_cursor = None
    if has_next and items:
        last_item = items[-1]
        last_is_followed = 0 if last_item.seller_id in followed_sellers else 1
        next_cursor = encode_cursor(last_is_followed, last_item.created_at, last_item.id)

    # Compute has_liked dynamically
    has_liked_map = {}
    if current_user and items:
        reel_ids = [r.id for r in items]
        liked_res = await db.execute(
            select(ReelLike.reel_id).where(
                ReelLike.buyer_id == current_user.id,
                ReelLike.reel_id.in_(reel_ids)
            )
        )
        liked_ids = set(liked_res.scalars().all())
        has_liked_map = {rid: True for rid in liked_ids}

    # Format feed items response
    feed_items = []
    for r in items:
        shop_name = r.seller.seller_profile.shop_name if r.seller.seller_profile else None
        feed_items.append(
            ReelFeedItem(
                id=r.id,
                video_url=r.video_url,
                thumbnail_url=r.thumbnail_url,
                caption=r.caption,
                duration_seconds=r.duration_seconds,
                like_count=r.like_count,
                comment_count=r.comment_count,
                has_liked=has_liked_map.get(r.id, False),
                product=ProductSummary(
                    id=r.product.id,
                    title=r.product.title,
                    price_paise=r.product.price_paise,
                    image_urls=r.product.image_urls,
                    is_active=r.product.is_active
                ),
                seller=SellerSummary(
                    shop_name=shop_name,
                    user_id=r.seller_id
                ),
                created_at=r.created_at
            )
        )

    return ReelFeedResponse(items=feed_items, next_cursor=next_cursor)


@router.get("/saved", response_model=list[ReelFeedItem])
async def get_saved_reels(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["buyer"])),
):
    query = (
        select(Reel)
        .join(ReelSave, Reel.id == ReelSave.reel_id)
        .join(Product, Reel.product_id == Product.id)
        .join(User, Reel.seller_id == User.id)
        .where(
            ReelSave.buyer_id == current_user.id,
            Reel.is_active == True,
            Product.is_active == True,
            User.is_active == True
        )
        .order_by(ReelSave.created_at.desc())
    )
    
    query = query.options(
        selectinload(Reel.product),
        selectinload(Reel.seller).selectinload(User.seller_profile)
    )
    
    res = await db.execute(query)
    reels = res.scalars().all()
    
    has_liked_map = {}
    if reels:
        reel_ids = [r.id for r in reels]
        liked_res = await db.execute(
            select(ReelLike.reel_id).where(
                ReelLike.buyer_id == current_user.id,
                ReelLike.reel_id.in_(reel_ids)
            )
        )
        liked_ids = set(liked_res.scalars().all())
        has_liked_map = {rid: True for rid in liked_ids}
        
    feed_items = []
    for r in reels:
        shop_name = r.seller.seller_profile.shop_name if r.seller.seller_profile else None
        feed_items.append(
            ReelFeedItem(
                id=r.id,
                video_url=r.video_url,
                thumbnail_url=r.thumbnail_url,
                caption=r.caption,
                duration_seconds=r.duration_seconds,
                like_count=r.like_count,
                comment_count=r.comment_count,
                has_liked=has_liked_map.get(r.id, False),
                product=ProductSummary(
                    id=r.product.id,
                    title=r.product.title,
                    price_paise=r.product.price_paise,
                    image_urls=r.product.image_urls,
                    is_active=r.product.is_active
                ),
                seller=SellerSummary(
                    shop_name=shop_name,
                    user_id=r.seller_id
                ),
                created_at=r.created_at
            )
        )
        
    return feed_items


@router.post("/{id}/like", status_code=status.HTTP_200_OK)
async def toggle_like_reel(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reel_res = await db.execute(select(Reel).where(Reel.id == id))
    reel = reel_res.scalar_one_or_none()
    if not reel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reel not found"
        )
    
    like_res = await db.execute(
        select(ReelLike).where(
            ReelLike.reel_id == id,
            ReelLike.buyer_id == current_user.id
        )
    )
    like = like_res.scalar_one_or_none()
    
    if like:
        await db.delete(like)
        await db.execute(
            update(Reel)
            .where(Reel.id == id)
            .values(like_count=Reel.like_count - 1)
        )
        liked = False
    else:
        new_like = ReelLike(reel_id=id, buyer_id=current_user.id)
        db.add(new_like)
        await db.execute(
            update(Reel)
            .where(Reel.id == id)
            .values(like_count=Reel.like_count + 1)
        )
        liked = True
        
    await db.flush()
    await db.refresh(reel)
    return {"liked": liked, "like_count": reel.like_count}


@router.post("/{id}/save", status_code=status.HTTP_200_OK)
async def toggle_save_reel(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["buyer"])),
):
    reel_res = await db.execute(select(Reel).where(Reel.id == id))
    reel = reel_res.scalar_one_or_none()
    if not reel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reel not found"
        )
        
    save_res = await db.execute(
        select(ReelSave).where(
            ReelSave.reel_id == id,
            ReelSave.buyer_id == current_user.id
        )
    )
    save = save_res.scalar_one_or_none()
    
    if save:
        await db.delete(save)
        saved = False
    else:
        new_save = ReelSave(reel_id=id, buyer_id=current_user.id)
        db.add(new_save)
        saved = True
        
    await db.flush()
    return {"saved": saved}


@router.post("/{id}/view", status_code=status.HTTP_200_OK)
@limiter.limit("60/minute", key_func=get_client_ip)
async def view_reel(
    id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    reel_res = await db.execute(select(Reel).where(Reel.id == id))
    reel = reel_res.scalar_one_or_none()
    if not reel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reel not found"
        )
        
    ip = get_client_ip(request)
    
    view_res = await db.execute(
        select(ReelView).where(
            ReelView.reel_id == id,
            ReelView.ip_address == ip
        )
    )
    view = view_res.scalar_one_or_none()
    
    now = datetime.utcnow()
    increment = False
    
    if view:
        if now - view.viewed_at >= timedelta(minutes=1):
            view.viewed_at = now
            increment = True
    else:
        new_view = ReelView(reel_id=id, ip_address=ip, viewed_at=now)
        db.add(new_view)
        increment = True
        
    if increment:
        await db.execute(
            update(Reel)
            .where(Reel.id == id)
            .values(view_count=Reel.view_count + 1)
        )
        await db.flush()
        await db.refresh(reel)
        
    return {"view_count": reel.view_count}


@router.post("/{id}/comment", response_model=ReelCommentRead, status_code=status.HTTP_201_CREATED)
async def comment_on_reel(
    id: uuid.UUID,
    payload: ReelCommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reel_res = await db.execute(select(Reel).where(Reel.id == id))
    reel = reel_res.scalar_one_or_none()
    if not reel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reel not found"
        )
        
    if current_user.role == "seller":
        if reel.seller_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sellers can only comment on their own reels."
            )
    elif current_user.role not in ["buyer", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to comment on reels."
        )
        
    comment = ReelComment(
        id=uuid.uuid4(),
        reel_id=id,
        author_id=current_user.id,
        body=payload.comment
    )
    db.add(comment)
    
    await db.execute(
        update(Reel)
        .where(Reel.id == id)
        .values(comment_count=Reel.comment_count + 1)
    )
    
    await db.flush()
    return comment


@router.get("/{id}/comments", response_model=ReelCommentsResponse)
async def get_reel_comments(
    id: uuid.UUID,
    limit: int = 10,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    limit = min(max(1, limit), 50)
    offset = max(0, offset)
    
    reel_res = await db.execute(select(Reel).where(Reel.id == id))
    reel = reel_res.scalar_one_or_none()
    if not reel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reel not found"
        )
        
    from sqlalchemy import func
    count_res = await db.execute(
        select(func.count(ReelComment.id)).where(ReelComment.reel_id == id)
    )
    total = count_res.scalar_one()
    
    comments_res = await db.execute(
        select(ReelComment)
        .where(ReelComment.reel_id == id)
        .order_by(ReelComment.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    comments = comments_res.scalars().all()
    
    return ReelCommentsResponse(
        items=list(comments),
        total=total,
        limit=limit,
        offset=offset
    )


@router.delete("/{id}/comments/{comment_id}", status_code=status.HTTP_200_OK)
async def delete_reel_comment(
    id: uuid.UUID,
    comment_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    comment_res = await db.execute(
        select(ReelComment).where(
            ReelComment.id == comment_id,
            ReelComment.reel_id == id
        )
    )
    comment = comment_res.scalar_one_or_none()
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )
        
    if comment.author_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to delete this comment."
        )
        
    await db.delete(comment)
    
    await db.execute(
        update(Reel)
        .where(Reel.id == id)
        .values(comment_count=Reel.comment_count - 1)
    )
    
    audit_log = AuditLog(
        user_id=current_user.id,
        event_type="reel_comment.deleted",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={
            "comment_id": str(comment.id),
            "reel_id": str(comment.reel_id),
            "author_id": str(comment.author_id),
            "deleted_by": str(current_user.id),
            "deleted_by_role": current_user.role
        }
    )
    db.add(audit_log)
    
    await db.flush()
    return {"detail": "Comment deleted successfully"}

