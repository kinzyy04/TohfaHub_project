import uuid
import base64
from datetime import datetime
from fastapi import HTTPException, status
from sqlalchemy import func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from app.models.category import Category
from app.models.product import Product
from app.models.user import User

async def get_all_categories(db: AsyncSession) -> list[Category]:
    result = await db.execute(
        select(Category).where(Category.is_active == True).order_by(Category.sort_order.asc())
    )
    return list(result.scalars().all())

def decode_home_cursor(cursor_str: str) -> tuple[datetime, uuid.UUID]:
    try:
        decoded_bytes = base64.b64decode(cursor_str.encode())
        decoded_str = decoded_bytes.decode()
        parts = decoded_str.split("|")
        return datetime.fromisoformat(parts[0]), uuid.UUID(parts[1])
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cursor format"
        )


def encode_home_cursor(created_at: datetime, item_id: uuid.UUID) -> str:
    cursor_str = f"{created_at.isoformat()}|{item_id}"
    return base64.b64encode(cursor_str.encode()).decode()


def get_search_clause(q_clean: str, is_sqlite: bool):
    words = [w for w in q_clean.split() if w]
    if not words:
        return Product.id == None, None

    if is_sqlite or len(q_clean) < 3:
        conditions = []
        for word in words:
            conditions.append(Product.title.ilike(f"%{word}%"))
            conditions.append(Product.description.ilike(f"%{word}%"))
        return or_(*conditions), None
    else:
        tsquery = func.plainto_tsquery('english', words[0])
        for word in words[1:]:
            tsquery = tsquery.op('||')(func.plainto_tsquery('english', word))
        return Product.search_vector.op('@@')(tsquery), tsquery


async def get_home_products(
    db: AsyncSession,
    limit: int = 20,
    cursor: str | None = None,
    search: str | None = None
) -> dict:
    limit = min(max(1, limit), 100)
    is_sqlite = db.bind.dialect.name == "sqlite"

    if search is not None:
        q = search.strip()
        offset = 0
        if cursor and cursor.startswith("search_offset|"):
            try:
                offset = int(cursor.split("|")[1])
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid cursor format"
                )

        clause, tsquery = get_search_clause(q, is_sqlite)

        sponsored_products = []
        if offset == 0:
            sponsored_stmt = (
                select(Product)
                .options(
                    joinedload(Product.category),
                    joinedload(Product.seller).joinedload(User.seller_profile)
                )
                .where(Product.is_active == True, Product.is_sponsored == True, clause)
            )
            if tsquery is not None:
                sponsored_stmt = sponsored_stmt.order_by(
                    func.ts_rank(Product.search_vector, tsquery).desc(),
                    Product.created_at.desc(),
                    Product.id.desc()
                )
            else:
                sponsored_stmt = sponsored_stmt.order_by(Product.created_at.desc(), Product.id.desc())
            sponsored_stmt = sponsored_stmt.limit(3)
            sponsored_res = await db.execute(sponsored_stmt)
            sponsored_products = list(sponsored_res.scalars().all())

        ns_stmt = (
            select(Product)
            .options(
                joinedload(Product.category),
                joinedload(Product.seller).joinedload(User.seller_profile)
            )
            .where(Product.is_active == True, Product.is_sponsored == False, clause)
        )
        if tsquery is not None:
            ns_stmt = ns_stmt.order_by(
                func.ts_rank(Product.search_vector, tsquery).desc(),
                Product.created_at.desc(),
                Product.id.desc()
            )
        else:
            ns_stmt = ns_stmt.order_by(Product.created_at.desc(), Product.id.desc())

        next_cursor = None
        if offset == 0:
            slots_left = limit - len(sponsored_products)
            if slots_left > 0:
                ns_stmt = ns_stmt.offset(0).limit(slots_left + 1)
                ns_res = await db.execute(ns_stmt)
                ns_products = list(ns_res.scalars().all())

                has_next = len(ns_products) > slots_left
                recent_ns = ns_products[:slots_left]
                recent_products = sponsored_products + recent_ns

                if has_next:
                    next_cursor = f"search_offset|{slots_left}"
            else:
                recent_products = sponsored_products[:limit]
                next_cursor = "search_offset|0"
        else:
            ns_stmt = ns_stmt.offset(offset).limit(limit + 1)
            ns_res = await db.execute(ns_stmt)
            ns_products = list(ns_res.scalars().all())

            has_next = len(ns_products) > limit
            recent_products = ns_products[:limit]

            if has_next:
                next_cursor = f"search_offset|{offset + limit}"

        return {
            "sponsored": sponsored_products if offset == 0 else [],
            "recent": recent_products,
            "next_cursor": next_cursor
        }

    # 1. Fetch sponsored products (always shown in full or up to 3 on first page)
    # To keep list deterministic but random-like, we sort by created_at desc, id desc.
    sponsored_stmt = (
        select(Product)
        .options(
            joinedload(Product.category),
            joinedload(Product.seller).joinedload(User.seller_profile)
        )
        .where(Product.is_active == True, Product.is_sponsored == True)
        .order_by(Product.created_at.desc(), Product.id.desc())
        .limit(3)
    )
    sponsored_res = await db.execute(sponsored_stmt)
    sponsored_products = list(sponsored_res.scalars().all())

    next_cursor = None

    if not cursor:
        # First page
        slots_left = limit - len(sponsored_products)
        if slots_left > 0:
            ns_stmt = (
                select(Product)
                .options(
                    joinedload(Product.category),
                    joinedload(Product.seller).joinedload(User.seller_profile)
                )
                .where(Product.is_active == True, Product.is_sponsored == False)
                .order_by(Product.created_at.desc(), Product.id.desc())
                .limit(slots_left + 1)
            )
            ns_res = await db.execute(ns_stmt)
            ns_products = list(ns_res.scalars().all())

            has_next = len(ns_products) > slots_left
            recent_ns = ns_products[:slots_left]
            recent_products = sponsored_products + recent_ns

            if has_next and recent_ns:
                last_item = recent_ns[-1]
                next_cursor = encode_home_cursor(last_item.created_at, last_item.id)
        else:
            recent_products = sponsored_products[:limit]
            # If there are non-sponsored products, we can paginate into them
            ns_exist_stmt = (
                select(Product.id)
                .where(Product.is_active == True, Product.is_sponsored == False)
                .limit(1)
            )
            ns_exist_res = await db.execute(ns_exist_stmt)
            if ns_exist_res.scalar_one_or_none() is not None:
                next_cursor = "ns_start"
    else:
        # Subsequent pages
        if cursor == "ns_start":
            ns_stmt = (
                select(Product)
                .options(
                    joinedload(Product.category),
                    joinedload(Product.seller).joinedload(User.seller_profile)
                )
                .where(Product.is_active == True, Product.is_sponsored == False)
                .order_by(Product.created_at.desc(), Product.id.desc())
                .limit(limit + 1)
            )
        else:
            # decode cursor, query only non-sponsored products
            cursor_created_at, cursor_id = decode_home_cursor(cursor)

            ns_stmt = (
                select(Product)
                .options(
                    joinedload(Product.category),
                    joinedload(Product.seller).joinedload(User.seller_profile)
                )
                .where(
                    Product.is_active == True,
                    Product.is_sponsored == False,
                    or_(
                        Product.created_at < cursor_created_at,
                        and_(
                            Product.created_at == cursor_created_at,
                            Product.id < cursor_id
                        )
                    )
                )
                .order_by(Product.created_at.desc(), Product.id.desc())
                .limit(limit + 1)
            )
        ns_res = await db.execute(ns_stmt)
        ns_products = list(ns_res.scalars().all())

        has_next = len(ns_products) > limit
        recent_products = ns_products[:limit]

        if has_next and recent_products:
            last_item = recent_products[-1]
            next_cursor = encode_home_cursor(last_item.created_at, last_item.id)

    return {
        "sponsored": sponsored_products if not cursor else [],
        "recent": recent_products,
        "next_cursor": next_cursor
    }

async def get_products_by_category(
    db: AsyncSession,
    category_slug: str,
    limit: int = 20,
    offset: int = 0,
) -> list[Product]:
    # Check if category exists
    cat_check = await db.execute(
        select(Category).where(Category.slug == category_slug, Category.is_active == True)
    )
    if not cat_check.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )

    stmt = (
        select(Product)
        .options(
            joinedload(Product.category),
            joinedload(Product.seller).joinedload(User.seller_profile)
        )
        .join(Category, Product.category_id == Category.id)
        .where(Product.is_active == True, Category.slug == category_slug)
        .order_by(Product.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())

async def search_products(
    db: AsyncSession,
    q: str,
    limit: int = 20,
    offset: int = 0,
) -> list[Product]:
    is_sqlite = db.bind.dialect.name == "sqlite"
    q_clean = q.strip()
    clause, tsquery = get_search_clause(q_clean, is_sqlite)

    stmt = (
        select(Product)
        .options(
            joinedload(Product.category),
            joinedload(Product.seller).joinedload(User.seller_profile)
        )
        .where(Product.is_active == True, clause)
    )

    if tsquery is not None:
        stmt = stmt.order_by(
            func.ts_rank(Product.search_vector, tsquery).desc(),
            Product.created_at.desc(),
            Product.id.desc()
        )
    else:
        stmt = stmt.order_by(Product.created_at.desc(), Product.id.desc())

    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())

