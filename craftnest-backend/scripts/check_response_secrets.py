"""
check_response_secrets.py — Security scan for secret leakage.

Starts the FastAPI app in-process using ASGI transport (no real server
needed), hits every public endpoint, and checks that none of the
following dangerous strings appear in the JSON response:

    password, password_hash, token_hash, JWT_SECRET

Usage:
    python scripts/check_response_secrets.py

Exits 0 if all checks pass, 1 if any FAIL.
"""

import sys
import asyncio
import json
import os
import io

# Force UTF-8 stdout to avoid cp1252 encoding errors on Windows terminals
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ── Make sure imports resolve from the project root ──────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Windows async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


import httpx
from httpx import AsyncClient, ASGITransport

# Bootstrap test database so the app starts cleanly
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./check_secrets_tmp.db")

from app.main import app  # noqa: E402 — must be imported after env setup
from app.core.database import Base, engine


# Strings that must NEVER appear in any public response JSON value
FORBIDDEN_KEYS = {"password", "password_hash", "token_hash", "JWT_SECRET"}


def _scan_json(data, path: str = "") -> list[str]:
    """
    Recursively walk JSON data and return a list of offending keypaths where
    a FORBIDDEN key is found (case-insensitive).
    """
    hits = []
    if isinstance(data, dict):
        for k, v in data.items():
            current_path = f"{path}.{k}" if path else k
            if k.lower() in {f.lower() for f in FORBIDDEN_KEYS}:
                hits.append(current_path)
            hits.extend(_scan_json(v, current_path))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            hits.extend(_scan_json(item, f"{path}[{i}]"))
    elif isinstance(data, str):
        # Also scan string values for the forbidden words
        lower_val = data.lower()
        for forbidden in FORBIDDEN_KEYS:
            if forbidden.lower() in lower_val:
                # Only flag if it looks like a key=value pattern or raw secret
                if "=" in data or len(data) > 60:
                    hits.append(f"{path} (value contains '{forbidden}')")
    return hits


async def run_checks():
    # Always start with a fresh SQLite DB so reruns don't hit unique constraints
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Seed a visible product so /browse/home and /browse/products/{id} have data
    # We do this by inserting directly via SQLAlchemy so we get a real product ID
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.models.user import User
    from app.models.category import Category
    from app.models.product import Product
    import uuid

    run_id = uuid.uuid4().hex[:8]
    Session = async_sessionmaker(bind=engine, expire_on_commit=False)
    product_id = None

    async with Session() as session:
        async with session.begin():
            # Create a category (slug must be unique — use run_id)
            cat = Category(
                slug=f"check-secrets-{run_id}",
                display_name="Check Secrets Cat",
                description="Auto seeded",
                icon_emoji="[search]",
            )
            session.add(cat)
            await session.flush()

            # Create a seller
            seller = User(
                email="checksecrets_seller@example.com",
                password_hash="$2b$12$fakehashforseedXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
                role="seller",
                is_active=True,
            )
            session.add(seller)
            await session.flush()

            # Create a product
            prod = Product(
                seller_id=seller.id,
                category_id=cat.id,
                title="Secret Scan Product",
                description="Used for secret leakage scan",
                price_paise=1000,
                stock=10,
                image_urls=["https://picsum.photos/400/300"],
                is_active=True,
            )
            session.add(prod)
            await session.flush()
            product_id = prod.id

    endpoints = [
        ("GET", "/health"),
        ("GET", "/api/v1/health"),
        ("GET", "/api/v1/browse/categories"),
        ("GET", "/api/v1/browse/home"),
        ("GET", f"/api/v1/browse/products/{product_id}" if product_id else "/api/v1/browse/home"),
    ]

    transport = ASGITransport(app=app)
    all_passed = True

    print()
    print("=" * 46)
    print("  CraftNest -- Response Secret Leakage Scan")
    print("=" * 46)
    print()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for method, path in endpoints:
            try:
                response = await client.request(method, path)
                label = f"{method} {path}"

                # Try to parse as JSON; non-JSON responses (HTML, plain text) pass by default
                try:
                    body = response.json()
                except Exception:
                    print(f"  PASS  {label}  [{response.status_code}] (non-JSON body)")
                    continue

                hits = _scan_json(body)
                if hits:
                    all_passed = False
                    print(f"  FAIL  {label}  [{response.status_code}]")
                    for h in hits:
                        print(f"          !  Leaked field: {h}")
                else:
                    print(f"  PASS  {label}  [{response.status_code}]")

            except Exception as exc:
                all_passed = False
                print(f"  FAIL  {method} {path}  -- exception: {exc}")

    print()
    if all_passed:
        print("[OK] All checks PASSED -- no secrets leaked.\n")
    else:
        print("[FAIL] One or more checks FAILED.\n")

    # Cleanup temp DB
    try:
        os.remove(os.path.join(PROJECT_ROOT, "check_secrets_tmp.db"))
    except OSError:
        pass

    return all_passed


if __name__ == "__main__":
    passed = asyncio.run(run_checks())
    sys.exit(0 if passed else 1)
