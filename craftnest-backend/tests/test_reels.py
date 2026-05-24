import os
import uuid
import pytest
import subprocess
import shutil
from datetime import datetime, timedelta, timezone
from io import BytesIO
from httpx import AsyncClient
from sqlalchemy.future import select
from app.models.category import Category
from app.models.product import Product
from app.models.user import User
from app.models.reel import Reel

# Helper to find FFmpeg binary location (same logic as router)
def get_ffmpeg_bin() -> str:
    if shutil.which("ffmpeg") is not None:
        return "ffmpeg"
    winget_packages_root = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    if os.path.exists(winget_packages_root):
        for root, dirs, files in os.walk(winget_packages_root):
            if "ffmpeg.exe" in files:
                return os.path.join(root, "ffmpeg.exe")
    return "ffmpeg"

def generate_test_video(duration: int, output_path: str):
    ffmpeg_bin = get_ffmpeg_bin()
    cmd = [
        ffmpeg_bin,
        "-y",
        "-f", "lavfi",
        "-i", f"color=c=blue:s=320x240:d={duration}",
        "-c:v", "libx264",
        "-t", str(duration),
        output_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

@pytest.fixture
async def seller_headers(seller_token: str) -> dict:
    return {"Authorization": f"Bearer {seller_token}"}

@pytest.fixture
async def buyer_headers(buyer_token: str) -> dict:
    return {"Authorization": f"Bearer {buyer_token}"}

@pytest.fixture
async def test_category(db) -> Category:
    cat = Category(
        slug="test-reels-cat",
        display_name="Test Reels Category",
        description="Category for testing reels",
        icon_emoji="🎬"
    )
    db.add(cat)
    await db.flush()
    return cat

@pytest.fixture
async def test_product(db, test_category, seller_token, client) -> Product:
    # Get seller user ID
    # We can decode the seller token or look up a seller user
    res = await db.execute(select(User).where(User.role == "seller"))
    seller_user = res.scalars().first()
    assert seller_user is not None
    
    prod = Product(
        seller_id=seller_user.id,
        category_id=test_category.id,
        title="Reel Product",
        description="A product to be highlighted by a reel",
        price_paise=5000,
        stock=5,
        image_urls=["https://example.com/p.jpg"],
        is_active=True
    )
    db.add(prod)
    await db.flush()
    return prod

@pytest.fixture(scope="session")
def video_file_5s(tmp_path_factory) -> str:
    tmp_dir = tmp_path_factory.mktemp("videos")
    video_path = os.path.join(tmp_dir, "test_5s.mp4")
    generate_test_video(5, video_path)
    return video_path

@pytest.fixture(scope="session")
def video_file_65s(tmp_path_factory) -> str:
    tmp_dir = tmp_path_factory.mktemp("videos")
    video_path = os.path.join(tmp_dir, "test_65s.mp4")
    generate_test_video(65, video_path)
    return video_path

# ==========================================
# POST /api/v1/reels/upload
# ==========================================

@pytest.mark.asyncio
async def test_upload_reel_success(client: AsyncClient, seller_headers: dict, test_product: Product, video_file_5s: str, db):
    # Read the generated video file
    with open(video_file_5s, "rb") as f:
        video_bytes = f.read()

    files = {"file": ("test_5s.mp4", video_bytes, "video/mp4")}
    data = {
        "product_id": str(test_product.id),
        "caption": "Check out this awesome product!"
    }

    response = await client.post(
        "/api/v1/reels/upload",
        files=files,
        data=data,
        headers=seller_headers
    )
    assert response.status_code == 201
    res_data = response.json()
    assert "id" in res_data
    assert res_data["product_id"] == str(test_product.id)
    assert res_data["caption"] == "Check out this awesome product!"
    assert res_data["duration_seconds"] == 5
    assert res_data["video_url"].startswith("/media/reels/")
    assert res_data["thumbnail_url"].startswith("/media/reels/")
    assert res_data["video_url"].endswith(".mp4")
    assert res_data["thumbnail_url"].endswith(".jpg")

    # Confirm files exist on disk
    video_disk_path = res_data["video_url"].lstrip("/")
    thumb_disk_path = res_data["thumbnail_url"].lstrip("/")
    assert os.path.exists(video_disk_path)
    assert os.path.exists(thumb_disk_path)

    # Clean up generated files
    if os.path.exists(video_disk_path):
        os.remove(video_disk_path)
    if os.path.exists(thumb_disk_path):
        os.remove(thumb_disk_path)

@pytest.mark.asyncio
async def test_upload_reel_unsupported_mime(client: AsyncClient, seller_headers: dict, test_product: Product):
    files = {"file": ("test.txt", b"plain text content", "text/plain")}
    data = {"product_id": str(test_product.id), "caption": "Unsupported"}

    response = await client.post(
        "/api/v1/reels/upload",
        files=files,
        data=data,
        headers=seller_headers
    )
    assert response.status_code == 415
    assert "Only MP4, QuickTime, and WebM" in response.json()["detail"]

@pytest.mark.asyncio
async def test_upload_reel_too_large(client: AsyncClient, seller_headers: dict, test_product: Product):
    # Create 31 MB of dummy bytes
    large_bytes = b"0" * (31 * 1024 * 1024)
    files = {"file": ("large.mp4", large_bytes, "video/mp4")}
    data = {"product_id": str(test_product.id), "caption": "Too large"}

    response = await client.post(
        "/api/v1/reels/upload",
        files=files,
        data=data,
        headers=seller_headers
    )
    assert response.status_code == 413
    detail = response.json()["detail"].lower()
    assert "exceeds" in detail or "too large" in detail

@pytest.mark.asyncio
async def test_upload_reel_too_long(client: AsyncClient, seller_headers: dict, test_product: Product, video_file_65s: str):
    with open(video_file_65s, "rb") as f:
        video_bytes = f.read()

    files = {"file": ("test_65s.mp4", video_bytes, "video/mp4")}
    data = {"product_id": str(test_product.id), "caption": "Too long"}

    response = await client.post(
        "/api/v1/reels/upload",
        files=files,
        data=data,
        headers=seller_headers
    )
    assert response.status_code == 422
    assert "exceeds the maximum limit of 60 seconds" in response.json()["detail"]

@pytest.mark.asyncio
async def test_upload_reel_non_seller(client: AsyncClient, buyer_headers: dict, test_product: Product, video_file_5s: str):
    with open(video_file_5s, "rb") as f:
        video_bytes = f.read()

    files = {"file": ("test_5s.mp4", video_bytes, "video/mp4")}
    data = {"product_id": str(test_product.id)}

    response = await client.post(
        "/api/v1/reels/upload",
        files=files,
        data=data,
        headers=buyer_headers
    )
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_upload_reel_product_not_found(client: AsyncClient, seller_headers: dict, video_file_5s: str):
    with open(video_file_5s, "rb") as f:
        video_bytes = f.read()

    files = {"file": ("test_5s.mp4", video_bytes, "video/mp4")}
    data = {"product_id": str(uuid.uuid4())}

    response = await client.post(
        "/api/v1/reels/upload",
        files=files,
        data=data,
        headers=seller_headers
    )
    assert response.status_code == 404
    assert "Product not found" in response.json()["detail"]

@pytest.mark.asyncio
async def test_upload_reel_not_owner(client: AsyncClient, seller_headers: dict, test_category: Category, db, video_file_5s: str):
    # Create another seller and their product
    from tests.conftest import create_user_token_helper
    other_seller_token = await create_user_token_helper(client, "seller")
    
    # Get other seller's user object
    res = await db.execute(select(User).where(User.email.like(f"seller_%")))
    sellers = res.scalars().all()
    # Find the one who matches the new token (created second)
    other_seller = sellers[-1]

    other_prod = Product(
        seller_id=other_seller.id,
        category_id=test_category.id,
        title="Other Product",
        description="Product of another seller",
        price_paise=1000,
        stock=1,
        is_active=True
    )
    db.add(other_prod)
    await db.flush()

    with open(video_file_5s, "rb") as f:
        video_bytes = f.read()

    files = {"file": ("test_5s.mp4", video_bytes, "video/mp4")}
    data = {"product_id": str(other_prod.id)}

    # Seller A tries to upload reel for Seller B's product
    response = await client.post(
        "/api/v1/reels/upload",
        files=files,
        data=data,
        headers=seller_headers
    )
    assert response.status_code == 403
    assert "You do not own the product" in response.json()["detail"]

# ==========================================
# DELETE /api/v1/reels/{id}
# ==========================================

@pytest.mark.asyncio
async def test_delete_reel_success(client: AsyncClient, seller_headers: dict, test_product: Product, db):
    # Pre-insert a reel directly in DB to delete
    res = await db.execute(select(User).where(User.role == "seller"))
    seller_user = res.scalars().first()

    reel = Reel(
        seller_id=seller_user.id,
        product_id=test_product.id,
        video_url="/media/reels/del.mp4",
        thumbnail_url="/media/reels/del.jpg",
        duration_seconds=10,
        caption="To be deleted",
        is_active=True
    )
    db.add(reel)
    await db.flush()

    response = await client.delete(f"/api/v1/reels/{reel.id}", headers=seller_headers)
    assert response.status_code == 200
    assert response.json()["detail"] == "Reel deleted successfully"

    # Verify soft delete in DB
    await db.refresh(reel)
    assert reel.is_active is False

@pytest.mark.asyncio
async def test_delete_reel_not_owner(client: AsyncClient, seller_headers: dict, test_product: Product, db):
    # Setup second seller
    from tests.conftest import create_user_token_helper
    other_seller_token = await create_user_token_helper(client, "seller")
    other_seller_headers = {"Authorization": f"Bearer {other_seller_token}"}
    
    res = await db.execute(select(User).where(User.role == "seller"))
    sellers = res.scalars().all()
    seller_user = sellers[0]

    reel = Reel(
        seller_id=seller_user.id,
        product_id=test_product.id,
        video_url="/media/reels/test.mp4",
        thumbnail_url="/media/reels/test.jpg",
        duration_seconds=10,
        caption="Owner is seller A",
        is_active=True
    )
    db.add(reel)
    await db.flush()

    # Seller B tries to delete Seller A's reel
    response = await client.delete(f"/api/v1/reels/{reel.id}", headers=other_seller_headers)
    assert response.status_code == 403
    assert "You do not own this reel" in response.json()["detail"]

@pytest.mark.asyncio
async def test_delete_reel_not_found(client: AsyncClient, seller_headers: dict):
    response = await client.delete(f"/api/v1/reels/{uuid.uuid4()}", headers=seller_headers)
    assert response.status_code == 404

# ==========================================
# GET /api/v1/reels/feed
# ==========================================

@pytest.mark.asyncio
async def test_reels_feed_pagination(client: AsyncClient, test_product: Product, db):
    # Get seller user
    res = await db.execute(select(User).where(User.role == "seller"))
    seller_user = res.scalars().first()

    # Seed 50 reels in DB with incremented timestamps so ordering is strict
    base_time = datetime.now(timezone.utc) - timedelta(days=10)
    reels = []
    for i in range(50):
        r = Reel(
            id=uuid.uuid4(),
            seller_id=seller_user.id,
            product_id=test_product.id,
            video_url=f"/media/reels/seed_{i}.mp4",
            thumbnail_url=f"/media/reels/seed_{i}.jpg",
            duration_seconds=15,
            caption=f"Seeded Reel {i}",
            is_active=True,
            created_at=base_time + timedelta(minutes=i)
        )
        db.add(r)
        reels.append(r)
    await db.flush()

    # Hit feed Page 1: limit 20
    response_p1 = await client.get("/api/v1/reels/feed?limit=20")
    assert response_p1.status_code == 200
    data_p1 = response_p1.json()
    assert len(data_p1["items"]) == 20
    assert data_p1["next_cursor"] is not None

    # Check order: newest first (Reel 49 down to Reel 30)
    for i in range(20):
        expected_index = 49 - i
        assert data_p1["items"][i]["caption"] == f"Seeded Reel {expected_index}"

    # Hit feed Page 2: limit 20
    cursor_1 = data_p1["next_cursor"]
    response_p2 = await client.get(f"/api/v1/reels/feed?limit=20&cursor={cursor_1}")
    assert response_p2.status_code == 200
    data_p2 = response_p2.json()
    assert len(data_p2["items"]) == 20
    assert data_p2["next_cursor"] is not None

    for i in range(20):
        expected_index = 29 - i
        assert data_p2["items"][i]["caption"] == f"Seeded Reel {expected_index}"

    # Hit feed Page 3: limit 20
    cursor_2 = data_p2["next_cursor"]
    response_p3 = await client.get(f"/api/v1/reels/feed?limit=20&cursor={cursor_2}")
    assert response_p3.status_code == 200
    data_p3 = response_p3.json()
    assert len(data_p3["items"]) == 10  # Remaining 10
    assert data_p3["next_cursor"] is None  # End of list

    for i in range(10):
        expected_index = 9 - i
        assert data_p3["items"][i]["caption"] == f"Seeded Reel {expected_index}"

    # Combine all items and assert no duplicates
    all_ids = [item["id"] for item in data_p1["items"]] + \
              [item["id"] for item in data_p2["items"]] + \
              [item["id"] for item in data_p3["items"]]
    assert len(all_ids) == 50
    assert len(set(all_ids)) == 50

@pytest.mark.asyncio
async def test_reels_feed_filters(client: AsyncClient, test_product: Product, db):
    # Setup seller, product, and reel
    res = await db.execute(select(User).where(User.role == "seller"))
    seller_user = res.scalars().first()

    reel = Reel(
        seller_id=seller_user.id,
        product_id=test_product.id,
        video_url="/media/reels/filter_test.mp4",
        thumbnail_url="/media/reels/filter_test.jpg",
        duration_seconds=10,
        caption="Filter Test Reel",
        is_active=True
    )
    db.add(reel)
    await db.flush()

    # 1. Initially, reel shows up in feed
    res_feed = await client.get("/api/v1/reels/feed?limit=5")
    assert any(item["id"] == str(reel.id) for item in res_feed.json()["items"])

    # 2. Deactivate reel -> shouldn't show up
    reel.is_active = False
    await db.flush()
    res_feed = await client.get("/api/v1/reels/feed?limit=5")
    assert not any(item["id"] == str(reel.id) for item in res_feed.json()["items"])

    # Reactivate reel
    reel.is_active = True
    await db.flush()

    # 3. Deactivate product -> shouldn't show up
    test_product.is_active = False
    await db.flush()
    res_feed = await client.get("/api/v1/reels/feed?limit=5")
    assert not any(item["id"] == str(reel.id) for item in res_feed.json()["items"])

    # Reactivate product
    test_product.is_active = True
    await db.flush()

    # 4. Deactivate seller -> shouldn't show up
    seller_user.is_active = False
    await db.flush()
    res_feed = await client.get("/api/v1/reels/feed?limit=5")
    assert not any(item["id"] == str(reel.id) for item in res_feed.json()["items"])

    # Cleanup/Reactivate seller to not pollute database state
    seller_user.is_active = True
    await db.flush()

# ==========================================
# RATE LIMITING
# ==========================================

@pytest.mark.asyncio
async def test_rate_limiting_upload_endpoint(client: AsyncClient, seller_headers: dict, test_product: Product, video_file_5s: str):
    # Rate limit is 10/hour. If we call it 11 times, the 11th should return 429.
    url = "/api/v1/reels/upload"
    
    with open(video_file_5s, "rb") as f:
        video_bytes = f.read()

    # Upload 10 times successfully
    for i in range(10):
        files = {"file": ("test_5s.mp4", video_bytes, "video/mp4")}
        data = {"product_id": str(test_product.id)}
        resp = await client.post(url, files=files, data=data, headers=seller_headers)
        assert resp.status_code == 201
        
        # Clean up files created on disk
        res_json = resp.json()
        video_disk_path = res_json["video_url"].lstrip("/")
        thumb_disk_path = res_json["thumbnail_url"].lstrip("/")
        if os.path.exists(video_disk_path):
            os.remove(video_disk_path)
        if os.path.exists(thumb_disk_path):
            os.remove(thumb_disk_path)

    # The 11th request must hit 429
    files = {"file": ("test_5s.mp4", video_bytes, "video/mp4")}
    data = {"product_id": str(test_product.id)}
    resp_limit = await client.post(url, files=files, data=data, headers=seller_headers)
    assert resp_limit.status_code == 429
    assert "Too many requests" in resp_limit.json()["detail"]


# ==========================================
# INTERACTIONS FIXTURE
# ==========================================

@pytest.fixture
async def test_reel(db, test_product: Product) -> Reel:
    # A generic active reel for testing interactions without ffmpeg overhead
    reel = Reel(
        id=uuid.uuid4(),
        seller_id=test_product.seller_id,
        product_id=test_product.id,
        video_url="/media/reels/mock.mp4",
        thumbnail_url="/media/reels/mock.jpg",
        duration_seconds=10,
        caption="Mock Reel for Interactions",
        is_active=True,
        view_count=0,
        like_count=0,
        comment_count=0
    )
    db.add(reel)
    await db.flush()
    return reel

# ==========================================
# LIKE ENDPOINT
# ==========================================

@pytest.mark.asyncio
async def test_like_reel_toggle(client: AsyncClient, buyer_headers: dict, test_reel: Reel):
    url = f"/api/v1/reels/{test_reel.id}/like"
    
    # 1. Like (increment)
    res_like = await client.post(url, headers=buyer_headers)
    assert res_like.status_code == 200
    data = res_like.json()
    assert data["liked"] is True
    assert data["like_count"] == 1
    
    # 2. Unlike (decrement)
    res_unlike = await client.post(url, headers=buyer_headers)
    assert res_unlike.status_code == 200
    data2 = res_unlike.json()
    assert data2["liked"] is False
    assert data2["like_count"] == 0

@pytest.mark.asyncio
async def test_like_reel_unauthenticated(client: AsyncClient, test_reel: Reel):
    res = await client.post(f"/api/v1/reels/{test_reel.id}/like")
    assert res.status_code == 401

@pytest.mark.asyncio
async def test_like_invalid_reel(client: AsyncClient, buyer_headers: dict):
    res = await client.post(f"/api/v1/reels/{uuid.uuid4()}/like", headers=buyer_headers)
    assert res.status_code == 404

# ==========================================
# SAVE ENDPOINT
# ==========================================

@pytest.mark.asyncio
async def test_save_reel_toggle(client: AsyncClient, buyer_headers: dict, test_reel: Reel):
    url = f"/api/v1/reels/{test_reel.id}/save"
    
    # 1. Save
    res_save = await client.post(url, headers=buyer_headers)
    assert res_save.status_code == 200
    assert res_save.json()["saved"] is True
    
    # 2. Unsave
    res_unsave = await client.post(url, headers=buyer_headers)
    assert res_unsave.status_code == 200
    assert res_unsave.json()["saved"] is False

@pytest.mark.asyncio
async def test_save_reel_seller_forbidden(client: AsyncClient, seller_headers: dict, test_reel: Reel):
    # Only buyers can save
    res = await client.post(f"/api/v1/reels/{test_reel.id}/save", headers=seller_headers)
    assert res.status_code == 403

@pytest.mark.asyncio
async def test_get_saved_reels(client: AsyncClient, buyer_headers: dict, test_reel: Reel):
    # Save the reel
    await client.post(f"/api/v1/reels/{test_reel.id}/save", headers=buyer_headers)
    
    # Get saved
    res = await client.get("/api/v1/reels/saved", headers=buyer_headers)
    assert res.status_code == 200
    items = res.json()
    assert len(items) >= 1
    assert any(item["id"] == str(test_reel.id) for item in items)
    
    # Verify has_liked defaults correctly in saved view
    item = next(i for i in items if i["id"] == str(test_reel.id))
    assert item["has_liked"] is False
    
    # Like it and verify it's updated in the saved list
    await client.post(f"/api/v1/reels/{test_reel.id}/like", headers=buyer_headers)
    res2 = await client.get("/api/v1/reels/saved", headers=buyer_headers)
    item2 = next(i for i in res2.json() if i["id"] == str(test_reel.id))
    assert item2["has_liked"] is True

# ==========================================
# COMMENT ENDPOINTS
# ==========================================

@pytest.mark.asyncio
async def test_comment_on_reel_buyer(client: AsyncClient, buyer_headers: dict, test_reel: Reel):
    url = f"/api/v1/reels/{test_reel.id}/comment"
    payload = {"comment": "This is a great reel!"}
    
    res = await client.post(url, json=payload, headers=buyer_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["body"] == payload["comment"]
    assert data["reel_id"] == str(test_reel.id)

@pytest.mark.asyncio
async def test_comment_seller_own_reel(client: AsyncClient, seller_headers: dict, test_reel: Reel):
    # The seller_headers fixture is the seller who owns test_product (and test_reel)
    url = f"/api/v1/reels/{test_reel.id}/comment"
    payload = {"comment": "Thanks for watching!"}
    
    res = await client.post(url, json=payload, headers=seller_headers)
    assert res.status_code == 201

@pytest.mark.asyncio
async def test_comment_seller_other_reel_forbidden(client: AsyncClient, test_reel: Reel):
    from tests.conftest import create_user_token_helper
    other_seller_token = await create_user_token_helper(client, "seller")
    other_seller_headers = {"Authorization": f"Bearer {other_seller_token}"}
    
    url = f"/api/v1/reels/{test_reel.id}/comment"
    payload = {"comment": "I cannot comment on this."}
    
    res = await client.post(url, json=payload, headers=other_seller_headers)
    assert res.status_code == 403

@pytest.mark.asyncio
async def test_get_reel_comments(client: AsyncClient, buyer_headers: dict, test_reel: Reel):
    # Add 2 comments
    for i in range(2):
        await client.post(
            f"/api/v1/reels/{test_reel.id}/comment",
            json={"comment": f"Comment {i}"},
            headers=buyer_headers
        )
        
    res = await client.get(f"/api/v1/reels/{test_reel.id}/comments")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["items"][0]["body"] == "Comment 0"
    assert data["items"][1]["body"] == "Comment 1"

@pytest.mark.asyncio
async def test_delete_comment_author(client: AsyncClient, buyer_headers: dict, test_reel: Reel):
    # Create comment
    res = await client.post(
        f"/api/v1/reels/{test_reel.id}/comment",
        json={"comment": "To be deleted"},
        headers=buyer_headers
    )
    comment_id = res.json()["id"]
    
    # Delete comment
    del_res = await client.delete(
        f"/api/v1/reels/{test_reel.id}/comments/{comment_id}",
        headers=buyer_headers
    )
    assert del_res.status_code == 200
    
    # Verify count decremented
    list_res = await client.get(f"/api/v1/reels/{test_reel.id}/comments")
    assert list_res.json()["total"] == 0

@pytest.mark.asyncio
async def test_delete_comment_forbidden(client: AsyncClient, buyer_headers: dict, seller_headers: dict, test_reel: Reel):
    # Buyer creates comment
    res = await client.post(
        f"/api/v1/reels/{test_reel.id}/comment",
        json={"comment": "Seller cannot delete this"},
        headers=buyer_headers
    )
    comment_id = res.json()["id"]
    
    # Seller tries to delete (forbidden, only admin or author)
    del_res = await client.delete(
        f"/api/v1/reels/{test_reel.id}/comments/{comment_id}",
        headers=seller_headers
    )
    assert del_res.status_code == 403

# ==========================================
# VIEW ENDPOINT
# ==========================================

@pytest.mark.asyncio
async def test_view_reel_rate_limited(client: AsyncClient, test_reel: Reel):
    url = f"/api/v1/reels/{test_reel.id}/view"
    
    # First view -> increments
    res1 = await client.post(url)
    assert res1.status_code == 200
    assert res1.json()["view_count"] == 1
    
    # Second view (same IP, immediately) -> rate limited, no increment
    res2 = await client.post(url)
    assert res2.status_code == 200
    assert res2.json()["view_count"] == 1


