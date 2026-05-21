import asyncio
from app.core.database import SessionLocal
from app.models.product import Product
from sqlalchemy import select

async def main():
    async with SessionLocal() as session:
        result = await session.execute(select(Product))
        products = result.scalars().all()
        if not products:
            print("No products found in DB.")
        for p in products:
            print(f"ID: {p.id} | Title: {p.title} | Price: {p.price_paise}")

if __name__ == "__main__":
    asyncio.run(main())
