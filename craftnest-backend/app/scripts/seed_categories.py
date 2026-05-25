import sys
import asyncio
from sqlalchemy import delete
from sqlalchemy.future import select
from passlib.context import CryptContext

# Set the selector event loop policy on Windows for psycopg async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.core.database import SessionLocal
from app.models.category import Category
from app.models.product import Product
from app.models.user import User
from app.models.profile import SellerProfile
from app.models.order import OrderItem, Order
from app.models.review import Review
from app.models.wishlist import Wishlist

CATEGORIES = [
    {"slug": "customised-gifts", "display_name": "Customised Gifts", "description": "Customized and personalized gifts for any occasion", "icon_emoji": "🎁", "sort_order": 1},
    {"slug": "hampers", "display_name": "Hampers", "description": "Gift hampers and curated boxes filled with goodies", "icon_emoji": "🧺", "sort_order": 2},
    {"slug": "couple", "display_name": "Couple", "description": "Romance, anniversary, and couple gifts", "icon_emoji": "💑", "sort_order": 3},
    {"slug": "festivals", "display_name": "Festivals", "description": "Festive items and decorations for holidays and celebrations", "icon_emoji": "🪔", "sort_order": 4},
    {"slug": "wedding-rituals", "display_name": "Wedding & Rituals", "description": "Wedding favors, ritual items, and ceremonial crafts", "icon_emoji": "👰", "sort_order": 5},
    {"slug": "handmade-letters", "display_name": "Handmade Letters", "description": "Beautifully handwritten letters, calligraphy, and envelopes", "icon_emoji": "✉️", "sort_order": 6},
    {"slug": "art-paintings", "display_name": "Art & Paintings", "description": "Original paintings, watercolor art, sketches, and canvases", "icon_emoji": "🎨", "sort_order": 7},
    {"slug": "frames", "display_name": "Frames", "description": "Handcrafted photo frames and customized wall frames", "icon_emoji": "🖼️", "sort_order": 8},
    {"slug": "home-decor", "display_name": "Home Décor", "description": "Decorative items, accents, and ornaments for home styling", "icon_emoji": "🏡", "sort_order": 9},
    {"slug": "candles", "display_name": "Candles", "description": "Scented, organic, and decorative hand-poured candles", "icon_emoji": "🕯️", "sort_order": 10},
    {"slug": "jewellery", "display_name": "Jewellery", "description": "Handmade necklaces, rings, bracelets, and earrings", "icon_emoji": "💍", "sort_order": 11},
    {"slug": "nail-art", "display_name": "Nail Art", "description": "Custom press-on nails and artistic nail accessories", "icon_emoji": "💅", "sort_order": 12},
    {"slug": "crochet", "display_name": "Crochet", "description": "Cozy knitted items, crochet amigurumi, and yarn crafts", "icon_emoji": "🧶", "sort_order": 13},
    {"slug": "fabric-crafts", "display_name": "Fabric Crafts", "description": "Handmade fabric accessories, quilts, and sewn goods", "icon_emoji": "🧵", "sort_order": 14},
    {"slug": "assignments", "display_name": "Assignments", "description": "Handwritten assignments, projects, and academic craft assistance", "icon_emoji": "📝", "sort_order": 15},
]

async def seed():
    async with SessionLocal() as session:
        print("Cleaning up old orders, reviews, wishlists, products, and categories...")
        await session.execute(delete(OrderItem))
        await session.execute(delete(Order))
        await session.execute(delete(Review))
        await session.execute(delete(Wishlist))
        await session.execute(delete(Product))
        await session.execute(delete(Category))
        await session.commit()
        print("Cleanup completed.")

        print("Seeding new categories...")
        cat_objects = []
        for cat_data in CATEGORIES:
            category = Category(**cat_data)
            session.add(category)
            cat_objects.append(category)
        await session.commit()
        print("Seeding categories completed successfully.")

        # Find or create a seller user so we can seed products
        res = await session.execute(select(User).where(User.role == "seller"))
        seller_user = res.scalars().first()
        if not seller_user:
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            seller_user = User(
                email="seller@example.com",
                password_hash=pwd_context.hash("SecurePassword123!"),
                role="seller"
            )
            session.add(seller_user)
            await session.commit()
            
            # Create seller profile
            profile = SellerProfile(
                user_id=seller_user.id,
                shop_name="Tohfa Artisans",
                shipping_days=3
            )
            session.add(profile)
            await session.commit()
            print("Created default seller user & profile.")

        # Seed products for customised-gifts, candles, art-paintings, jewellery, and crochet
        cats_by_slug = {c.slug: c.id for c in cat_objects}

        products_data = [
            {
                "seller_id": seller_user.id,
                "category_id": cats_by_slug["customised-gifts"],
                "title": "Customized Wooden Memory Box",
                "description": "A beautifully hand-engraved wooden box for storing your precious memories. Personalized with names/dates.",
                "price_paise": 150000,
                "stock": 10,
                "image_urls": ["/media/products/placeholder.jpg"],
                "is_active": True,
                "is_sponsored": True
            },
            {
                "seller_id": seller_user.id,
                "category_id": cats_by_slug["candles"],
                "title": "Lavender & Vanilla Scented Candle",
                "description": "Hand-poured soy wax candle infused with lavender and vanilla essential oils for ultimate relaxation.",
                "price_paise": 45000,
                "stock": 20,
                "image_urls": ["/media/products/placeholder.jpg"],
                "is_active": True,
                "is_sponsored": False
            },
            {
                "seller_id": seller_user.id,
                "category_id": cats_by_slug["crochet"],
                "title": "Chubby Crochet Bumblebee",
                "description": "Super soft, hand-crocheted bumblebee plushie. Perfect for home decor or a cute gift.",
                "price_paise": 65000,
                "stock": 15,
                "image_urls": ["/media/products/placeholder.jpg"],
                "is_active": True,
                "is_sponsored": False
            },
            {
                "seller_id": seller_user.id,
                "category_id": cats_by_slug["art-paintings"],
                "title": "Botanical Watercolor Painting",
                "description": "Original A4 watercolor painting featuring delicate wildflowers. Signed by the artist.",
                "price_paise": 220000,
                "stock": 1,
                "image_urls": ["/media/products/placeholder.jpg"],
                "is_active": True,
                "is_sponsored": True
            }
        ]

        print("Seeding initial products...")
        for p_data in products_data:
            prod = Product(**p_data)
            session.add(prod)
        await session.commit()
        print("Initial products seeded successfully.")

if __name__ == "__main__":
    asyncio.run(seed())

