import sys
import asyncio

# Set the selector event loop policy on Windows for psycopg async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uuid
import time
from fastapi import FastAPI, Depends, status, Request
from fastapi.responses import JSONResponse
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
from app.routers.notifications import router as notifications_router







app = FastAPI(
    title="CraftNest API",
    description="Backend API for CraftNest marketplace",
    version="0.1.0",
    lifespan=lifespan,
)

# Prometheus instrumentation – one‑line library
from prometheus_fastapi_instrumentator import Instrumentator
# Register metrics and expose endpoint
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

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

from starlette.formparsers import MultiPartException

@app.exception_handler(MultiPartException)
async def multipart_exception_handler(request: Request, exc: MultiPartException):
    logger.warn("Multipart parsing error", error=exc.message)
    message = exc.message.lower()
    if "exceeded" in message or "too many" in message:
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={"detail": exc.message}
        )
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": exc.message}
    )

from starlette.exceptions import HTTPException
from fastapi.exception_handlers import http_exception_handler

@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    # Check if this is a wrapped MultiPartException or general body parsing error
    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    message = str(exc.detail).lower()
    is_multipart_err = (
        isinstance(cause, MultiPartException)
        or (exc.status_code == 400 and ("exceeded" in message or "too many" in message or "parsing the body" in message))
    )
    if is_multipart_err:
        logger.warn("Request body parsing failed", error=str(cause or exc.detail))
        detail_msg = cause.message if (cause and isinstance(cause, MultiPartException)) else exc.detail
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={"detail": detail_msg}
        )
    return await http_exception_handler(request, exc)

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
app.include_router(notifications_router)







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


# ---------------------------------------------------------------------------
# Task 1 — Security response headers
# Applied to EVERY response to harden the HTTP layer.
# ---------------------------------------------------------------------------
_SECURITY_HEADERS: dict[str, str] = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "img-src 'self' data: https://picsum.photos; "
        "media-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "script-src 'self'"
    ),
}

@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Attach security-hardening headers to every outgoing response."""
    response = await call_next(request)
    for header, value in _SECURITY_HEADERS.items():
        response.headers[header] = value
    return response


# ---------------------------------------------------------------------------
# Task 2 — Request body size limit (1 MB for JSON endpoints)
# File-upload endpoints already enforce their own limits via the multipart
# handler; this guard covers JSON / form payloads.
# ---------------------------------------------------------------------------
_MAX_BODY_BYTES = 1_048_576  # 1 MB

@app.middleware("http")
async def body_size_limit_middleware(request: Request, call_next):
    """
    Reject requests whose Content-Length header exceeds 1 MB before the body
    is read.  Multipart/form-data (file uploads) are exempt because they
    enforce their own limits at the router level.
    """
    content_type = request.headers.get("content-type", "")
    is_multipart = "multipart/form-data" in content_type

    if not is_multipart:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > _MAX_BODY_BYTES:
                    return JSONResponse(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content={"detail": "Request body exceeds the 1 MB limit."},
                    )
            except ValueError:
                pass  # malformed header — let FastAPI handle it

    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"https?://.*" if (settings.ENVIRONMENT == "development" and "pytest" not in sys.modules) else None,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)

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



