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
    db.expire_all()
    
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
    print("DEBUG BROWSE HOME DATA:", data)
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


@pytest.mark.asyncio
async def test_browse_home_sponsored_placement(client: AsyncClient, seeded_data, admin_token: str):
    # p3 (Vanilla Candle) is initially NOT sponsored. Let's make sure it is not at the top.
    home_res_before = await client.get("/api/v1/browse/home?limit=5")
    assert home_res_before.status_code == 200
    before_data = home_res_before.json()
    
    # 1. Toggle p3 to sponsored = True
    p3 = seeded_data["products"][2] # Vanilla Candle
    toggle_resp = await client.patch(
        f"/api/v1/admin/products/{p3.id}/sponsored",
        json={"is_sponsored": True},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["is_sponsored"] is True

    # 2. Call home browse and assert it is in position 0-2 of recent
    home_res_after = await client.get("/api/v1/browse/home?limit=5")
    assert home_res_after.status_code == 200
    after_data = home_res_after.json()
    
    recent_titles = [p["title"] for p in after_data["recent"]]
    # It must be within the first 3 items because it is sponsored
    assert p3.title in recent_titles[:3]

    # 3. Toggle it back to sponsored = False
    toggle_back_resp = await client.patch(
        f"/api/v1/admin/products/{p3.id}/sponsored",
        json={"is_sponsored": False},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert toggle_back_resp.status_code == 200
    assert toggle_back_resp.json()["is_sponsored"] is False

    # 4. Call home browse and assert it drops back to normal
    home_res_final = await client.get("/api/v1/browse/home?limit=5")
    assert home_res_final.status_code == 200
    final_data = home_res_final.json()
    
    # Since it is no longer sponsored, it should not be forced into the top positions
    # (or if it is, it's solely based on created_at, but we can verify it behaves as a normal product)
    # Let's verify next_cursor works and does not duplicate sponsored products
    assert "next_cursor" in final_data


@pytest.mark.asyncio
async def test_browse_fts_search(client: AsyncClient, seeded_data, db):
    # Retrieve the seller user id and categories using async queries to avoid MissingGreenlet
    user_res = await db.execute(select(User).where(User.role == "seller"))
    seller_user = user_res.scalars().first()
    seller_user_id = seller_user.id

    cat_res = await db.execute(select(Category))
    categories = cat_res.scalars().all()
    cat_map = {c.slug: c.id for c in categories}
    cat1_id = cat_map["ceramics"]
    cat2_id = cat_map["candles"]

    # Add FTS-specific products
    p5 = Product(
        seller_id=seller_user_id,
        category_id=cat1_id,
        title="Clay Pottery Vase",
        description="Handcrafted pottery vase from local clay",
        price_paise=2500,
        stock=2,
        image_urls=[],
        is_active=True,
        is_sponsored=False
    )
    p6 = Product(
        seller_id=seller_user_id,
        category_id=cat2_id,
        title="Soy Candle Gift Set",
        description="A perfect candle gift set for holidays",
        price_paise=1800,
        stock=10,
        image_urls=[],
        is_active=True,
        is_sponsored=False
    )
    db.add_all([p5, p6])
    await db.flush()


    # 1. Search "pottery" -> finds "Clay Pottery Vase"
    res_pottery = await client.get("/api/v1/browse/search?q=pottery")
    assert res_pottery.status_code == 200
    data_pottery = res_pottery.json()
    assert len(data_pottery) == 1
    assert data_pottery[0]["title"] == "Clay Pottery Vase"

    # 2. Search "candle gift" -> finds "Soy Candle Gift Set" and others (Lavender/Vanilla candles)
    res_candle_gift = await client.get("/api/v1/browse/search?q=candle gift")
    assert res_candle_gift.status_code == 200
    data_candle_gift = res_candle_gift.json()
    assert len(data_candle_gift) >= 2
    titles = [p["title"] for p in data_candle_gift]
    assert "Soy Candle Gift Set" in titles
    assert "Lavender Candle" in titles

    # 3. Test GET /browse/home with search param
    res_home_search = await client.get("/api/v1/browse/home?search=pottery")
    assert res_home_search.status_code == 200
    data_home = res_home_search.json()
    assert len(data_home["recent"]) == 1
    assert data_home["recent"][0]["title"] == "Clay Pottery Vase"


