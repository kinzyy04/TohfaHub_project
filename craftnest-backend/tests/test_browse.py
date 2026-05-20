import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.future import select
from app.models.category import Category
from app.models.product import Product
from app.models.profile import SellerProfile
from app.models.user import User

@pytest.fixture
async def seeded_data(client: AsyncClient, db):
    # 1. Create categories
    cat1 = Category(
        slug="ceramics",
        display_name="Ceramics",
        description="Clay and pottery",
        sort_order=2
    )
    cat2 = Category(
        slug="candles",
        display_name="Candles",
        description="Scented candles",
        sort_order=1
    )
    db.add_all([cat1, cat2])
    await db.flush()

    # 2. Create seller user
    from tests.conftest import create_user_token_helper
    seller_token = await create_user_token_helper(client, "seller")
    
    user_res = await db.execute(select(User).where(User.role == "seller"))
    seller_user = user_res.scalars().first()
    
    # Set up Seller Profile
    prof_res = await db.execute(select(SellerProfile).where(SellerProfile.user_id == seller_user.id))
    profile = prof_res.scalar_one_or_none()
    if not profile:
        profile = SellerProfile(
            user_id=seller_user.id,
            shop_name="Glow Artisans",
            shipping_days=3
        )
        db.add(profile)
    else:
        profile.shop_name = "Glow Artisans"
        profile.shipping_days = 3
    await db.flush()

    # 3. Create products
    p1 = Product(
        seller_id=seller_user.id,
        category_id=cat1.id,
        title="Ceramic Mug",
        description="Handmade ceramic coffee mug",
        price_paise=1200,
        stock=10,
        image_urls=["http://example.com/mug.jpg"],
        is_active=True,
        is_sponsored=True
    )
    
    p2 = Product(
        seller_id=seller_user.id,
        category_id=cat2.id,
        title="Lavender Candle",
        description="Relaxing aromatherapy candle",
        price_paise=800,
        stock=5,
        image_urls=["http://example.com/candle.jpg"],
        is_active=True,
        is_sponsored=True
    )
    
    p3 = Product(
        seller_id=seller_user.id,
        category_id=cat2.id,
        title="Vanilla Candle",
        description="Sweet vanilla scent",
        price_paise=950,
        stock=4,
        image_urls=[],
        is_active=True,
        is_sponsored=False
    )
    
    p4 = Product(
        seller_id=seller_user.id,
        category_id=cat1.id,
        title="Broken Pot",
        description="This is inactive",
        price_paise=100,
        stock=1,
        image_urls=[],
        is_active=False,
        is_sponsored=False
    )
    
    db.add_all([p1, p2, p3, p4])
    await db.flush()
    
    return {
        "seller": seller_user,
        "categories": [cat1, cat2],
        "products": [p1, p2, p3, p4]
    }

# ==========================================
# GET /api/v1/browse/categories
# ==========================================

@pytest.mark.asyncio
async def test_browse_categories(client: AsyncClient, seeded_data):
    response = await client.get("/api/v1/browse/categories")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    # Check sort order (candles sort_order=1, ceramics sort_order=2)
    assert data[0]["slug"] == "candles"
    assert data[1]["slug"] == "ceramics"
    # Confirm shape
    for cat in data:
        assert "id" in cat
        assert "slug" in cat
        assert "display_name" in cat
        assert "description" in cat
        assert "icon_emoji" in cat
        assert "sort_order" in cat

# ==========================================
# GET /api/v1/browse/home
# ==========================================

@pytest.mark.asyncio
async def test_browse_home(client: AsyncClient, seeded_data):
    response = await client.get("/api/v1/browse/home")
    assert response.status_code == 200
    data = response.json()
    assert "sponsored" in data
    assert "recent" in data
    
    # Check sponsored shape and data
    sponsored = data["sponsored"]
    assert len(sponsored) <= 3
    for p in sponsored:
        assert p["category_slug"] in ["ceramics", "candles"]
        assert p["shop_name"] == "Glow Artisans"
        assert p["shipping_days"] == 3
        assert "id" in p
        assert "title" in p
        assert "price_paise" in p
        assert "image_urls" in p

    # Check recent (should only contain active products: 3 of them, not the inactive p4)
    recent = data["recent"]
    assert len(recent) == 3
    # Check that inactive Broken Pot (p4) is not in there
    titles = [x["title"] for x in recent]
    assert "Broken Pot" not in titles
    assert "Ceramic Mug" in titles
    assert "Lavender Candle" in titles
    assert "Vanilla Candle" in titles

# ==========================================
# GET /api/v1/browse/category/{slug}
# ==========================================

@pytest.mark.asyncio
async def test_browse_category_products(client: AsyncClient, seeded_data):
    # Ceramics category
    response = await client.get("/api/v1/browse/category/ceramics")
    assert response.status_code == 200
    data = response.json()
    # p1 (Ceramic Mug) is active. p4 (Broken Pot) is inactive. So only p1 should return.
    assert len(data) == 1
    assert data[0]["title"] == "Ceramic Mug"
    assert data[0]["shop_name"] == "Glow Artisans"
    assert data[0]["category_slug"] == "ceramics"

    # Candles category
    response_candles = await client.get("/api/v1/browse/category/candles")
    assert response_candles.status_code == 200
    data_candles = response_candles.json()
    assert len(data_candles) == 2 # p2 and p3 are active

    # Non-existent category -> 404
    response_fake = await client.get("/api/v1/browse/category/fake-slug")
    assert response_fake.status_code == 404

# ==========================================
# GET /api/v1/browse/search
# ==========================================

@pytest.mark.asyncio
async def test_browse_search_validation(client: AsyncClient, seeded_data):
    # Missing q -> 422
    res_missing = await client.get("/api/v1/browse/search")
    assert res_missing.status_code == 422

    # Too short -> 422
    res_short = await client.get("/api/v1/browse/search?q=a")
    assert res_short.status_code == 422

    # Too long -> 422
    res_long = await client.get(f"/api/v1/browse/search?q={'a'*51}")
    assert res_long.status_code == 422

@pytest.mark.asyncio
async def test_browse_search_queries(client: AsyncClient, seeded_data):
    # Test valid search matching title
    res_mug = await client.get("/api/v1/browse/search?q=mug")
    assert res_mug.status_code == 200
    data_mug = res_mug.json()
    assert len(data_mug) == 1
    assert data_mug[0]["title"] == "Ceramic Mug"

    # Test valid search matching description
    res_arom = await client.get("/api/v1/browse/search?q=aromatherapy")
    assert res_arom.status_code == 200
    data_arom = res_arom.json()
    assert len(data_arom) == 1
    assert data_arom[0]["title"] == "Lavender Candle"

    # Test SQL injection attack payload string
    sql_inj = "'; DROP TABLE products;--"
    res_inj = await client.get(f"/api/v1/browse/search?q={sql_inj}")
    # Should safely return 200 but empty list, without breaking or executing SQL
    assert res_inj.status_code == 200
    assert len(res_inj.json()) == 0

    # Verify products table still exists and operates normally
    res_check = await client.get("/api/v1/browse/home")
    assert res_check.status_code == 200
    assert len(res_check.json()["recent"]) == 3
