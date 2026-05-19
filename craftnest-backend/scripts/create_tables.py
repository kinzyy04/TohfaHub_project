import asyncio
from app.core.database import Base, engine
from app.models.user import User
from app.models.item import Item

async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created successfully in production database.")

if __name__ == "__main__":
    asyncio.run(main())
