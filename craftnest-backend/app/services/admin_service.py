import uuid
import time
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, text, or_, update
from sqlalchemy.orm import selectinload, joinedload
from fastapi import HTTPException, status

from app.models.user import User
from app.models.product import Product
from app.models.order import Order, OrderItem
from app.models.profile import SellerProfile
from app.models.reel import Reel
from app.models.category import Category
from app.services.audit_service import log_event
from app.services.notification_service import create_notification

_cache = {}

def clear_stats_cache():
    _cache.clear()

async def get_admin_stats(db: AsyncSession) -> dict:
    now = time.time()
    if "stats" in _cache:
        data, expires_at = _cache["stats"]
        if now < expires_at:
            return data

    # 1. Users bucket
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    stmt_users = select(
        func.count().label("total"),
        func.sum(case((User.role == 'buyer', 1), else_=0)).label("buyers"),
        func.sum(case((User.role == 'seller', 1), else_=0)).label("sellers"),
        func.sum(case((User.created_at >= today_start, 1), else_=0)).label("new_today")
    )
    res_users = (await db.execute(stmt_users)).one()
    
    users_data = {
        "total": res_users.total or 0,
        "new_today": int(res_users.new_today or 0),
        "buyers": int(res_users.buyers or 0),
        "sellers": int(res_users.sellers or 0),
    }

    # 2. Products bucket
    stmt_products = select(
        func.count().label("total"),
        func.sum(case((Product.is_active == True, 1), else_=0)).label("active")
    )
    res_products = (await db.execute(stmt_products)).one()
    products_data = {
        "total": res_products.total or 0,
        "active": int(res_products.active or 0),
    }

    # 3. Orders bucket & GMV
    stmt_orders = select(
        func.count().label("total"),
        func.sum(case((Order.status == 'pending', 1), else_=0)).label("pending"),
        func.sum(case((Order.status == 'processing', 1), else_=0)).label("processing"),
        func.sum(case((Order.status == 'shipped', 1), else_=0)).label("shipped"),
        func.sum(case((Order.status == 'delivered', 1), else_=0)).label("delivered"),
        func.sum(case((Order.status == 'delivered', Order.total_paise), else_=0)).label("gmv_paise")
    )
    res_orders = (await db.execute(stmt_orders)).one()
    orders_data = {
        "total": res_orders.total or 0,
        "pending": int(res_orders.pending or 0),
        "processing": int(res_orders.processing or 0),
        "shipped": int(res_orders.shipped or 0),
        "delivered": int(res_orders.delivered or 0),
    }
    gmv_paise = int(res_orders.gmv_paise or 0)

    # 4. Top Sellers (delivered orders only, sum of price_snapshot_paise * quantity)
    stmt_top_sellers = (
        select(
            OrderItem.seller_id,
            SellerProfile.shop_name,
            func.count(func.distinct(OrderItem.order_id)).label("order_count"),
            func.sum(OrderItem.price_snapshot_paise * OrderItem.quantity).label("gmv_paise")
        )
        .join(Order, Order.id == OrderItem.order_id)
        .join(SellerProfile, SellerProfile.user_id == OrderItem.seller_id, isouter=True)
        .where(Order.status == 'delivered')
        .group_by(OrderItem.seller_id, SellerProfile.shop_name)
        .order_by(text("gmv_paise DESC"))
        .limit(5)
    )
    res_sellers = (await db.execute(stmt_top_sellers)).all()
    top_sellers = []
    for row in res_sellers:
        top_sellers.append({
            "seller_id": str(row.seller_id),
            "shop_name": row.shop_name if row.shop_name is not None else "Artisan Shop",
            "order_count": int(row.order_count or 0),
            "gmv_paise": int(row.gmv_paise or 0)
        })

    # 5. Daily New Users (Last 7 Days)
    today = datetime.now(timezone.utc).date()
    last_7_days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    daily_map = {date.strftime("%Y-%m-%d"): 0 for date in last_7_days}
    
    start_date = today - timedelta(days=6)
    start_datetime = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    stmt_daily_users = (
        select(
            func.date(User.created_at).label("date"),
            func.count().label("count")
        )
        .where(User.created_at >= start_datetime)
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at).asc())
    )
    res_daily = (await db.execute(stmt_daily_users)).all()
    for row in res_daily:
        # SQLite can return string dates, Postgres returns date objects
        date_str = str(row.date)
        if date_str in daily_map:
            daily_map[date_str] = row.count

    daily_new_users_7d = [{"date": d, "count": c} for d, c in daily_map.items()]

    stats = {
        "users": users_data,
        "products": products_data,
        "orders": orders_data,
        "gmv_paise": gmv_paise,
        "top_sellers": top_sellers,
        "daily_new_users_7d": daily_new_users_7d
    }

    _cache["stats"] = (stats, time.time() + 60.0)
    return stats


async def list_sellers(
    db: AsyncSession,
    search: str | None = None,
    is_active: bool | None = None,
    page: int = 1,
    limit: int = 20,
) -> list[dict]:
    # 1. product_count per seller
    product_count_sub = (
        select(Product.seller_id, func.count(Product.id).label("product_count"))
        .group_by(Product.seller_id)
        .subquery()
    )

    # 2. order_count per seller (distinct orders from order_items)
    order_count_sub = (
        select(OrderItem.seller_id, func.count(func.distinct(OrderItem.order_id)).label("order_count"))
        .group_by(OrderItem.seller_id)
        .subquery()
    )

    # Main query
    stmt = (
        select(
            User.id.label("user_id"),
            User.email,
            SellerProfile.shop_name,
            User.is_active,
            func.coalesce(product_count_sub.c.product_count, 0).label("product_count"),
            func.coalesce(order_count_sub.c.order_count, 0).label("order_count"),
            User.created_at.label("joined_at")
        )
        .join(SellerProfile, SellerProfile.user_id == User.id, isouter=True)
        .join(product_count_sub, product_count_sub.c.seller_id == User.id, isouter=True)
        .join(order_count_sub, order_count_sub.c.seller_id == User.id, isouter=True)
        .where(User.role == 'seller')
    )

    # Filters
    if search:
        search_pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                SellerProfile.shop_name.ilike(search_pattern),
                User.email.ilike(search_pattern)
            )
        )

    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)

    # Pagination and sorting
    stmt = stmt.order_by(User.created_at.desc())
    stmt = stmt.offset((page - 1) * limit).limit(limit)

    res = await db.execute(stmt)
    results = res.all()

    return [
        {
            "user_id": row.user_id,
            "email": row.email,
            "shop_name": row.shop_name,
            "is_active": row.is_active,
            "product_count": row.product_count,
            "order_count": row.order_count,
            "joined_at": row.joined_at,
        }
        for row in results
    ]


async def get_seller_details(db: AsyncSession, user_id: uuid.UUID) -> dict:
    # 1. Fetch user (ensure role == 'seller')
    user_stmt = (
        select(User)
        .options(selectinload(User.seller_profile))
        .where(User.id == user_id, User.role == "seller")
    )
    user_res = await db.execute(user_stmt)
    user = user_res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller not found")

    # 2. Fetch all products
    prod_stmt = (
        select(Product)
        .where(Product.seller_id == user_id)
        .order_by(Product.created_at.desc())
    )
    prod_res = await db.execute(prod_stmt)
    products = prod_res.scalars().all()

    # 3. Fetch recent 5 orders involving their products
    order_stmt = (
        select(Order)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .where(OrderItem.seller_id == user_id)
        .distinct()
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc())
        .limit(5)
    )
    order_res = await db.execute(order_stmt)
    orders = order_res.scalars().all()

    return {
        "user": user,
        "seller_profile": user.seller_profile,
        "products": products,
        "recent_orders": orders
    }


async def ban_seller(
    db: AsyncSession,
    user_id: uuid.UUID,
    reason: str,
    admin_id: uuid.UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> User:
    # 1. Fetch user
    stmt = select(User).where(User.id == user_id)
    res = await db.execute(stmt)
    target_user = res.scalar_one_or_none()

    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller not found.")

    if target_user.role == "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin accounts cannot be banned.")

    if target_user.role != "seller":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is not a seller.")

    if not target_user.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Seller is already banned.")

    # 2. Perform updates atomically
    async with db.begin_nested():
        target_user.is_active = False
        
        await db.execute(
            update(Product)
            .where(Product.seller_id == user_id)
            .values(is_active=False)
        )
        
        await db.execute(
            update(Reel)
            .where(Reel.seller_id == user_id)
            .values(is_active=False)
        )

        await log_event(
            db=db,
            event_type="admin.seller.banned",
            user_id=admin_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "reason": reason,
                "seller_id": str(user_id)
            }
        )
        await db.flush()

    return target_user


async def unban_seller(
    db: AsyncSession,
    user_id: uuid.UUID,
    admin_id: uuid.UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> User:
    # 1. Fetch user
    stmt = select(User).where(User.id == user_id)
    res = await db.execute(stmt)
    target_user = res.scalar_one_or_none()

    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller not found.")

    if target_user.role != "seller":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is not a seller.")

    if target_user.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Seller is not banned.")

    # 2. Perform updates atomically
    async with db.begin_nested():
        target_user.is_active = True
        
        await db.execute(
            update(Product)
            .where(Product.seller_id == user_id)
            .values(is_active=True)
        )
        
        await db.execute(
            update(Reel)
            .where(Reel.seller_id == user_id)
            .values(is_active=True)
        )

        await log_event(
            db=db,
            event_type="admin.seller.unbanned",
            user_id=admin_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "seller_id": str(user_id)
            }
        )
        await db.flush()

    return target_user


async def list_orders(
    db: AsyncSession,
    status: str | None = None,
    buyer_email: str | None = None,
    seller_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    limit: int = 20,
) -> dict:
    stmt = select(Order).join(User, Order.buyer_id == User.id)

    if seller_id is not None:
        stmt = stmt.join(OrderItem, OrderItem.order_id == Order.id).where(OrderItem.seller_id == seller_id)
        stmt = stmt.distinct()

    if status is not None:
        stmt = stmt.where(Order.status == status)

    if buyer_email is not None:
        stmt = stmt.where(User.email.ilike(f"%{buyer_email}%"))

    if date_from is not None:
        stmt = stmt.where(Order.created_at >= date_from)

    if date_to is not None:
        stmt = stmt.where(Order.created_at <= date_to)

    # Count total rows (before limit/offset)
    count_stmt = select(func.count(func.distinct(Order.id))).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # Ordering and Pagination
    stmt = stmt.order_by(Order.created_at.desc())
    stmt = stmt.offset((page - 1) * limit).limit(limit)

    # Eager load buyer and items -> seller -> profile
    stmt = stmt.options(
        joinedload(Order.buyer),
        selectinload(Order.items).joinedload(OrderItem.seller).joinedload(User.seller_profile)
    )

    res = await db.execute(stmt)
    orders = res.scalars().all()

    items_out = []
    for order in orders:
        shop_names = []
        seen_shops = set()
        for item in order.items:
            shop_name = None
            if item.seller and item.seller.seller_profile:
                shop_name = item.seller.seller_profile.shop_name
            if not shop_name:
                shop_name = "Artisan Shop"
            if shop_name not in seen_shops:
                seen_shops.add(shop_name)
                shop_names.append(shop_name)

        seller_shop_name = ", ".join(shop_names)

        items_out.append({
            "id": order.id,
            "buyer_id": order.buyer_id,
            "buyer_email": order.buyer.email,
            "status": order.status,
            "total_paise": order.total_paise,
            "shipping_address": order.shipping_address,
            "seller_note": order.seller_note,
            "tracking_code": order.tracking_code,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
            "seller_shop_name": seller_shop_name,
            "items": order.items
        })

    return {
        "items": items_out,
        "total": total,
        "page": page,
        "page_size": limit
    }


async def force_order_status(
    db: AsyncSession,
    order_id: uuid.UUID,
    new_status: str,
    admin_note: str | None,
    admin_id: uuid.UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Order:
    stmt = select(Order).where(Order.id == order_id)
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    allowed_statuses = {'pending', 'awaiting_payment', 'paid_offline', 'processing', 'shipped', 'delivered', 'cancelled', 'refunded'}
    if new_status not in allowed_statuses:
        raise HTTPException(status_code=422, detail=f"Invalid status. Must be one of: {', '.join(sorted(allowed_statuses))}")

    old_status = order.status

    async with db.begin_nested():
        order.status = new_status
        if admin_note is not None:
            if order.seller_note:
                order.seller_note = f"{order.seller_note}\n[Admin Note] {admin_note}"
            else:
                order.seller_note = f"[Admin Note] {admin_note}"
        db.add(order)
        await db.flush()

        await log_event(
            db=db,
            event_type="admin.order.status_override",
            user_id=admin_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "order_id": str(order_id),
                "from": old_status,
                "to": new_status,
                "admin_note": admin_note
            }
        )
        await db.flush()

        # Notify buyer when admin forces shipped or delivered
        if new_status == "shipped":
            await create_notification(
                db=db,
                user_id=order.buyer_id,
                type="order.shipped",
                title="Your order is on the way",
                body=f"Tracking: {order.tracking_code or 'see seller note'}.",
                related_id=order.id,
            )
            await db.flush()
        elif new_status == "delivered":
            await create_notification(
                db=db,
                user_id=order.buyer_id,
                type="order.delivered",
                title="Order delivered!",
                body="Leave a review to help others.",
                related_id=order.id,
            )
            await db.flush()

    stmt_reload = select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    res_reload = await db.execute(stmt_reload)
    return res_reload.scalar_one()


async def flag_order_refund(
    db: AsyncSession,
    order_id: uuid.UUID,
    note: str,
    admin_id: uuid.UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Order:
    stmt = select(Order).where(Order.id == order_id)
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    async with db.begin_nested():
        order.status = "refunded"
        if order.seller_note:
            order.seller_note = f"{order.seller_note}\n[Refund Note] {note}"
        else:
            order.seller_note = f"[Refund Note] {note}"
        db.add(order)
        await db.flush()

        await log_event(
            db=db,
            event_type="admin.order.refund_flagged",
            user_id=admin_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "order_id": str(order_id),
                "note": note
            }
        )
        await db.flush()

    stmt_reload = select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    res_reload = await db.execute(stmt_reload)
    return res_reload.scalar_one()


async def list_all_categories(db: AsyncSession) -> list[Category]:
    result = await db.execute(
        select(Category).order_by(Category.sort_order.asc())
    )
    return list(result.scalars().all())


async def create_category(
    db: AsyncSession,
    slug: str,
    display_name: str,
    description: str,
    icon_emoji: str | None,
    sort_order: int,
    admin_id: uuid.UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Category:
    slug_check = await db.execute(
        select(Category).where(Category.slug == slug)
    )
    if slug_check.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Category slug already exists")

    async with db.begin_nested():
        category = Category(
            slug=slug,
            display_name=display_name,
            description=description,
            icon_emoji=icon_emoji,
            sort_order=sort_order,
            is_active=True
        )
        db.add(category)
        await db.flush()

        await log_event(
            db=db,
            event_type="admin.category.created",
            user_id=admin_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "category_id": str(category.id),
                "slug": slug,
                "display_name": display_name
            }
        )
        await db.flush()

    return category


async def update_category(
    db: AsyncSession,
    category_id: uuid.UUID,
    slug: str | None,
    display_name: str | None,
    description: str | None,
    icon_emoji: str | None,
    sort_order: int | None,
    admin_id: uuid.UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Category:
    stmt = select(Category).where(Category.id == category_id)
    res = await db.execute(stmt)
    category = res.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    if slug is not None and slug != category.slug:
        slug_check = await db.execute(
            select(Category).where(Category.slug == slug)
        )
        if slug_check.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Category slug already exists")

    async with db.begin_nested():
        if slug is not None:
            category.slug = slug
        if display_name is not None:
            category.display_name = display_name
        if description is not None:
            category.description = description
        if icon_emoji is not None:
            category.icon_emoji = icon_emoji
        if sort_order is not None:
            category.sort_order = sort_order

        db.add(category)
        await db.flush()

        await log_event(
            db=db,
            event_type="admin.category.updated",
            user_id=admin_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "category_id": str(category.id),
                "slug": category.slug,
                "display_name": category.display_name
              }
        )
        await db.flush()

    return category


async def delete_category(
    db: AsyncSession,
    category_id: uuid.UUID,
    admin_id: uuid.UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    stmt = select(Category).where(Category.id == category_id)
    res = await db.execute(stmt)
    category = res.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    if not category.is_active:
        raise HTTPException(status_code=400, detail="Category is already inactive")

    prod_check = await db.execute(
        select(func.count(Product.id)).where(Product.category_id == category_id)
    )
    product_count = prod_check.scalar_one()
    if product_count > 0:
        raise HTTPException(status_code=409, detail="Cannot delete category with associated products")

    async with db.begin_nested():
        category.is_active = False
        db.add(category)
        await db.flush()

        await log_event(
            db=db,
            event_type="admin.category.deleted",
            user_id=admin_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "category_id": str(category_id),
                "slug": category.slug
            }
        )
        await db.flush()

    return {"detail": "Category deleted successfully"}


async def toggle_product_sponsored(
    db: AsyncSession,
    product_id: uuid.UUID,
    is_sponsored: bool,
    admin_id: uuid.UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Product:
    stmt = select(Product).where(Product.id == product_id)
    res = await db.execute(stmt)
    product = res.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    async with db.begin_nested():
        product.is_sponsored = is_sponsored
        db.add(product)
        await db.flush()

        await log_event(
            db=db,
            event_type="admin.product.sponsored_toggled",
            user_id=admin_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "product_id": str(product_id),
                "is_sponsored": is_sponsored
            }
        )
        await db.flush()

    await db.refresh(product)
    sp_result = await db.execute(
        select(SellerProfile.shop_name).where(SellerProfile.user_id == product.seller_id)
    )
    product.shop_name = sp_result.scalar_one_or_none()

    return product

