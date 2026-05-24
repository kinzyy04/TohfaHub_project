"""
integrity_check.py — Nightly database integrity checker for CraftNest.

Checks performed:
  1. Every user with role='seller' has a matching seller_profiles row.
  2. Every user with role='buyer'  has a matching buyer_profiles row.
  3. Every product's seller_id references a user with role in ('seller','admin').
  4. Every order_item's product_id references an existing product.
  5. No order has total_paise of 0 or negative.

Usage:
    python scripts/integrity_check.py

Exits 0 if ALL checks pass, 1 if ANY fail.
Schedule with cron / Task Scheduler:
    0 4 * * * /path/to/.venv/bin/python /path/to/scripts/integrity_check.py \
        >> /var/log/craftnest_integrity.log 2>&1

Windows Task Scheduler equivalent is documented in scripts/README_scheduler.txt.
"""

import sys
import asyncio
import os
import io
from datetime import datetime, timezone

# UTF-8 stdout for Windows terminals
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Windows async policy
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import text
from app.core.database import engine


# ---------------------------------------------------------------------------
# Check definitions
# Each check is a (label, SQL) pair.  SQL must return rows ONLY when there
# is a violation — zero rows means PASS.
# ---------------------------------------------------------------------------

CHECKS = [
    (
        "Check 1 — Sellers missing seller_profiles row",
        text("""
            SELECT u.id, u.email
            FROM   users u
            LEFT JOIN seller_profiles sp ON sp.user_id = u.id
            WHERE  u.role = 'seller'
              AND  sp.user_id IS NULL
            LIMIT  10;
        """),
    ),
    (
        "Check 2 — Buyers missing buyer_profiles row",
        text("""
            SELECT u.id, u.email
            FROM   users u
            LEFT JOIN buyer_profiles bp ON bp.user_id = u.id
            WHERE  u.role = 'buyer'
              AND  bp.user_id IS NULL
            LIMIT  10;
        """),
    ),
    (
        "Check 3 — Products with invalid seller_id (role not seller/admin)",
        text("""
            SELECT p.id, p.title, p.seller_id
            FROM   products p
            JOIN   users u ON u.id = p.seller_id
            WHERE  u.role NOT IN ('seller', 'admin')
            LIMIT  10;
        """),
    ),
    (
        "Check 4 — Order items referencing non-existent products",
        text("""
            SELECT oi.id, oi.order_id, oi.product_id
            FROM   order_items oi
            LEFT JOIN products p ON p.id = oi.product_id
            WHERE  p.id IS NULL
            LIMIT  10;
        """),
    ),
    (
        "Check 5 — Orders with total_paise <= 0",
        text("""
            SELECT id, buyer_id, total_paise, status
            FROM   orders
            WHERE  total_paise <= 0
            LIMIT  10;
        """),
    ),
]


async def run() -> bool:
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print()
    print("=" * 56)
    print("  CraftNest -- Nightly Integrity Check")
    print(f"  Run at: {now}")
    print("=" * 56)
    print()

    all_passed = True

    async with engine.connect() as conn:
        for label, query in CHECKS:
            try:
                rows = (await conn.execute(query)).fetchall()
                if rows:
                    all_passed = False
                    print(f"  FAIL  {label}")
                    for row in rows:
                        print(f"        violating row: {dict(row._mapping)}")
                else:
                    print(f"  PASS  {label}")
            except Exception as exc:
                all_passed = False
                print(f"  FAIL  {label}")
                print(f"        ERROR running check: {exc}")

    print()
    if all_passed:
        print("[OK] All integrity checks PASSED.\n")
    else:
        print("[FAIL] One or more integrity checks FAILED.\n")
        print(
            "Action required: investigate the violations above.\n"
            "Re-run after fixing: python scripts/integrity_check.py\n"
        )

    return all_passed


if __name__ == "__main__":
    ok = asyncio.run(run())
    sys.exit(0 if ok else 1)
