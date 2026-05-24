from fastapi import Request
from slowapi import Limiter
from jose import jwt
from app.core.config import settings

def get_client_ip(request: Request) -> str:
    """Resolves client IP address. Supports X-Forwarded-For if TRUSTED_PROXY is enabled."""
    if settings.TRUSTED_PROXY:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # X-Forwarded-For can contain multiple IPs; get the client (first) one
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"

# Initialize Limiter with our custom proxy-aware key function, disabled in development/testing
limiter = Limiter(key_func=get_client_ip, enabled=settings.ENVIRONMENT not in ("development", "testing"))

def user_or_ip_key_func(request: Request) -> str:
    """Returns a rate-limit key based on authenticated user ID, or falls back to client IP."""
    ip = get_client_ip(request)
    
    auth_header = request.headers.get("authorization")
    if auth_header:
        try:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1]
                # Decode using the new JWT_SECRET key
                payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.ALGORITHM])
                user_id = payload.get("sub")
                if user_id:
                    return f"user_{user_id}"
        except Exception:
            pass
            
    return f"ip_{ip}"

def rate_limit_by_user(times: str):
    """Decorator wrapper that rate limits by user_id if authenticated, else by client IP."""
    return limiter.limit(times, key_func=user_or_ip_key_func)
