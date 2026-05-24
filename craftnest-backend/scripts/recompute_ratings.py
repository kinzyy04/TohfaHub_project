"""
recompute_ratings.py — One-off script to recompute avg_rating and review_count
for ALL products from source-of-truth review rows.

Useful to:
  - Fix any drift caused by the old incremental floating-point formula.
  - Heal after a data import or manual DB edit.
  - Validate that the live numbers match what the reviews table says.

Usage:
    python scripts/recompute_ratings.py [--dry-run]

Options:
    --dry-run   Print what would change without committing.

Exits 0 on success, 1 on error.
"""

import sys
import asyncio
import os
import io
import argparse

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
# SQL: single UPDATE that recomputes all products in one shot
# ---------------------------------------------------------------------------
# PostgreSQL variant uses a correlated sub-select with numeric rounding.
# SQLite variant uses ROUND(CAST(... AS REAL), 2) which is portable.

_SQL_RECOMPUTE_PG = text("""
UPDATE products p
SET
    avg_rating   = sub.avg_r,
    review_count = sub.cnt
FROM (
    SELECT
        product_id,
        ROUND(AVG(rating)::numeric, 2) AS avg_r,
        COUNT(*)                       AS cnt
    FROM   reviews
    GROUP  BY product_id
) sub
WHERE p.id = sub.product_id;
""")

# Zero out products that have NO reviews (in case reviews were deleted).
_SQL_ZERO_NO_REVIEWS_PG = text("""
UPDATE products
SET avg_rating = NULL, review_count = 0
WHERE id NOT IN (SELECT DISTINCT product_id FROM reviews)
  AND (avg_rating IS NOT NULL OR review_count != 0);
""")

# SQLite does not support UPDATE...FROM; use a correlated subquery instead.
_SQL_RECOMPUTE_SQLITE = text("""
UPDATE products
SET
    avg_rating   = (
        SELECT ROUND(CAST(AVG(rating) AS REAL), 2)
        FROM   reviews
        WHERE  product_id = products.id
    ),
    review_count = (
        SELECT COUNT(*)
        FROM   reviews
        WHERE  product_id = products.id
    );
""")


async def run(dry_run: bool = False) -> bool:
    print()
    print("=" * 52)
    print("  CraftNest -- Recompute Product Ratings")
    print("=" * 52)
    print()

    async with engine.connect() as conn:
        dialect = conn.dialect.name
        print(f"  Database dialect : {dialect}")

        # Count products before
        total_products = (
            await conn.execute(text("SELECT COUNT(*) FROM products"))
        ).scalar_one()
        total_reviews = (
            await conn.execute(text("SELECT COUNT(*) FROM reviews"))
        ).scalar_one()
        print(f"  Products         : {total_products}")
        print(f"  Reviews          : {total_reviews}")
        print()

        if dry_run:
            # Show current vs computed for any that would change
            if dialect == "postgresql":
                drift_q = text("""
                    SELECT
                        p.id,
                        p.avg_rating        AS current_avg,
                        p.review_count      AS current_cnt,
                        ROUND(AVG(r.rating)::numeric, 2) AS computed_avg,
                        COUNT(r.id)         AS computed_cnt
                    FROM products p
                    LEFT JOIN reviews r ON r.product_id = p.id
                    GROUP BY p.id, p.avg_rating, p.review_count
                    HAVING
                        ROUND(AVG(r.rating)::numeric, 2) IS DISTINCT FROM p.avg_rating
                        OR COUNT(r.id) != p.review_count
                    ORDER BY p.id
                    LIMIT 50;
                """)
            else:
                drift_q = text("""
                    SELECT
                        p.id,
                        p.avg_rating                     AS current_avg,
                        p.review_count                   AS current_cnt,
                        ROUND(CAST(AVG(r.rating) AS REAL), 2) AS computed_avg,
                        COUNT(r.id)                      AS computed_cnt
                    FROM products p
                    LEFT JOIN reviews r ON r.product_id = p.id
                    GROUP BY p.id, p.avg_rating, p.review_count
                    HAVING
                        ROUND(CAST(AVG(r.rating) AS REAL), 2) != COALESCE(p.avg_rating, -1)
                        OR COUNT(r.id) != p.review_count
                    ORDER BY p.id
                    LIMIT 50;
                """)
            rows = (await conn.execute(drift_q)).fetchall()
            if rows:
                print(f"  [DRY-RUN] {len(rows)} product(s) would be updated:")
                for r in rows:
                    print(
                        f"    id={r[0]}  "
                        f"avg: {r[1]} -> {r[3]}  "
                        f"count: {r[2]} -> {r[4]}"
                    )
            else:
                print("  [DRY-RUN] No drift detected -- all products are consistent.")
            print()
            return True

        # -- LIVE run --
        async with engine.begin() as wconn:
            if dialect == "postgresql":
                res = await wconn.execute(_SQL_RECOMPUTE_PG)
                updated = res.rowcount
                await wconn.execute(_SQL_ZERO_NO_REVIEWS_PG)
            else:
                res = await wconn.execute(_SQL_RECOMPUTE_SQLITE)
                updated = res.rowcount

        print(f"  Updated {updated} product row(s).")
        print()
        print("[OK] Rating recompute complete -- all products are now exact.")
        print()
        return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recompute product avg_rating / review_count from reviews table."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without committing.",
    )
    args = parser.parse_args()

    ok = asyncio.run(run(dry_run=args.dry_run))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
