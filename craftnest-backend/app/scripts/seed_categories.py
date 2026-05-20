import sys
import asyncio
from sqlalchemy.future import select

# Set the selector event loop policy on Windows for psycopg async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.core.database import SessionLocal
from app.models.category import Category

CATEGORIES = [
    {"slug": "jewellery", "display_name": "Jewellery", "description": "Handcrafted necklaces, rings, bracelets, and earrings", "icon_emoji": "💍", "sort_order": 1},
    {"slug": "candles", "display_name": "Candles", "description": "Scented and decorative hand-poured candles", "icon_emoji": "🕯️", "sort_order": 2},
    {"slug": "pottery", "display_name": "Pottery", "description": "Handmade ceramic mugs, bowls, and vases", "icon_emoji": "🏺", "sort_order": 3},
    {"slug": "prints", "display_name": "Prints & Art", "description": "Original art prints, posters, and illustrations", "icon_emoji": "🎨", "sort_order": 4},
    {"slug": "soaps", "display_name": "Soaps & Bath", "description": "Natural organic soaps and bath products", "icon_emoji": "🧼", "sort_order": 5},
    {"slug": "clothing", "display_name": "Clothing", "description": "Handmade apparel, scarves, and accessories", "icon_emoji": "👕", "sort_order": 6},
    {"slug": "leather", "display_name": "Leather Goods", "description": "Premium handcrafted leather wallets, belts, and accessories", "icon_emoji": "💼", "sort_order": 7},
    {"slug": "bags", "display_name": "Bags & Totes", "description": "Hand-stitched bags, purses, and backpacks", "icon_emoji": "👜", "sort_order": 8},
    {"slug": "journals", "display_name": "Journals & Notebooks", "description": "Hand-bound journals and stationery products", "icon_emoji": "📓", "sort_order": 9},
    {"slug": "knitting", "display_name": "Knitting & Crochet", "description": "Cozy knitted scarves, hats, and plush toys", "icon_emoji": "🧶", "sort_order": 10},
    {"slug": "woodwork", "display_name": "Woodwork", "description": "Carved wooden boards, utensils, and home decor", "icon_emoji": "🪵", "sort_order": 11},
    {"slug": "mixed", "display_name": "Mixed Media", "description": "Unique items combining different artistic mediums", "icon_emoji": "🌀", "sort_order": 12},
]

async def seed():
    async with SessionLocal() as session:
        for cat_data in CATEGORIES:
            result = await session.execute(
                select(Category).where(Category.slug == cat_data["slug"])
            )
            existing = result.scalar_one_or_none()
            if existing:
                print(f"Category {cat_data['slug']} already exists. Skipping.")
                continue
            
            category = Category(**cat_data)
            session.add(category)
            print(f"Added category: {cat_data['slug']}")
        await session.commit()
    print("Seeding completed successfully.")

if __name__ == "__main__":
    asyncio.run(seed())
