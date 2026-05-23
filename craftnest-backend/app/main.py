import sys
import asyncio

# Set the selector event loop policy on Windows for psycopg async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uuid
import time
from fastapi import FastAPI, Depends, status, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from contextlib import asynccontextmanager
from jose import jwt

from app.core.database import engine, get_db, SessionLocal
from app.core.config import settings
from fastapi.middleware.cors import CORSMiddleware
from app.core.logging import logger
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.core.rate_limit import limiter
from slowapi.errors import RateLimitExceeded

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup log
    logger.info("DB engine ready")
    
    # Check DB user or initialize SQLite
    if "sqlite" in str(engine.url):
        try:
            logger.info("Using SQLite database. Initializing tables...")
            from app.core.database import Base
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("SQLite database tables initialized successfully.")
        except Exception as e:
            logger.error("Failed to initialize SQLite database tables", error=str(e))
    else:
        # Check DB user to prevent connecting as superuser
        try:
            async with SessionLocal() as session:
                result = await session.execute(text("SELECT current_user;"))
                current_user = result.scalar()
                
                if current_user and ("postgres" in current_user.lower() or "superuser" in current_user.lower()):
                    logger.critical(
                        "Security risk: Application connected to DB as highly privileged user. Refusing to start.",
                        current_user=current_user
                    )
                    sys.exit(1)
                else:
                    logger.info("Connected as DB user", current_user=current_user)
        except SystemExit:
            raise
        except Exception as e:
            logger.error("Failed to verify database user during startup", error=str(e))

    yield
    # Clean shutdown
    await engine.dispose()
    logger.info("DB engine disposed cleanly")

import app.models  # Ensure all models are loaded before routers
from app.routers.auth import router as auth_router
from app.routers.items import router as items_router
from app.routers.profiles import router as profiles_router
from app.routers.products import router as products_router
from app.routers.browse import router as browse_router
from app.routers.uploads import router as uploads_router
from app.routers.wishlist import router as wishlist_router
from app.routers.reels import router as reels_router
from app.routers.users import router as users_router
from app.routers.orders import router as orders_router
from app.routers.reviews import router as reviews_router
from app.routers.admin import router as admin_router







app = FastAPI(
    title="CraftNest API",
    description="Backend API for CraftNest marketplace",
    version="0.1.0",
    lifespan=lifespan,
)

# Attach limiter to application state
app.state.limiter = limiter

# Register rate limit exceeded exception handler
@app.exception_handler(RateLimitExceeded)
async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    retry_after = getattr(exc, "retry_after", 60)
    return JSONResponse(
        status_code=429,
        content={"detail": f"Too many requests, try again in {retry_after} seconds"},
        headers={"Retry-After": str(retry_after)}
    )

app.include_router(auth_router)
app.include_router(items_router)
app.include_router(profiles_router)
app.include_router(products_router)
app.include_router(browse_router)
app.include_router(uploads_router)
app.include_router(wishlist_router)
app.include_router(reels_router)
app.include_router(users_router)
app.include_router(orders_router)
app.include_router(reviews_router)
app.include_router(admin_router)







@app.middleware("http")
async def structlog_middleware(request: Request, call_next):
    # 1. Generate or extract Request ID
    request_id = request.headers.get("x-request-id")
    if not request_id:
        request_id = str(uuid.uuid4())
        
    # 2. Extract user identity if Authorization header is present
    user_id = None
    auth_header = request.headers.get("authorization")
    if auth_header:
        try:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1]
                # Use JWT_SECRET instead of legacy SECRET_KEY
                payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.ALGORITHM])
                user_id = payload.get("sub")
        except Exception:
            user_id = None

    # 3. Bind request context variables
    ip = request.client.host if request.client else "unknown"
    bind_contextvars(
        request_id=request_id,
        user_id=user_id,
        path=request.url.path,
        method=request.method,
        ip=ip
    )

    start_time = time.perf_counter()
    try:
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        
        status_code = response.status_code
        if status_code >= 400:
            logger.warn(
                "Request completed with error status",
                status_code=status_code,
                duration_ms=duration_ms,
            )
        else:
            logger.info(
                "Request completed successfully",
                status_code=status_code,
                duration_ms=duration_ms,
            )
            
        response.headers["X-Request-Id"] = request_id
        return response
        
    except Exception as exc:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.error(
            "Request failed with unhandled exception",
            exception_type=type(exc).__name__,
            exception_message=str(exc),
            status_code=500,
            duration_ms=duration_ms,
        )
        raise exc
    finally:
        clear_contextvars()


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"https?://.*" if (settings.ENVIRONMENT == "development" and "pytest" not in sys.modules) else None,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)

@app.get("/")
async def root():
    return RedirectResponse(url="/home.html")

@app.get("/health", tags=["Health Check"])
async def health_check():
    return {"status": "ok"}

@app.get("/api/v1/health", tags=["Health Check"])
async def api_health_check():
    return {"status": "ok"}

@app.get("/api/v1/health/db", tags=["Health Check"])
async def health_db_check(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        return {"db": "ok"}
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"db": "error", "detail": str(e)},
        )


import os
os.makedirs("media/products", exist_ok=True)
os.makedirs("media/reels", exist_ok=True)
app.mount("/media", StaticFiles(directory="media"), name="media")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")



