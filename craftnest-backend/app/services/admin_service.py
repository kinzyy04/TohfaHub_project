import uuid
import time
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, text

from app.models.user import User
from app.models.product import Product
from app.models.order import Order, OrderItem
from app.models.profile import SellerProfile

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
