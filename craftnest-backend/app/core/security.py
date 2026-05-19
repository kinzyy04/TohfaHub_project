import uuid
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.core.config import settings

# Password hashing configuration using Argon2id with recommended parameters
pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
    argon2__time_cost=3,
    argon2__memory_cost=65536,
    argon2__parallelism=2
)

def hash_password(plain_password: str) -> str:
    """Generate a hash from a plain text password using Argon2."""
    return pwd_context.hash(plain_password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain text password against its Argon2 hash."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False

# Keep alias for backward compatibility if any parts of the code still import it
get_password_hash = hash_password

def create_access_token(user_id: uuid.UUID, role: str) -> str:
    """Create a signed JWT access token with a 15-minute expiry."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode = {
        "exp": expire,
        "sub": str(user_id),
        "role": role
    }
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET,
        algorithm="HS256"
    )
    return encoded_jwt

def create_refresh_token(user_id: uuid.UUID) -> tuple[str, datetime]:
    """Generate a cryptographically secure raw refresh token and its expiry (30 days)."""
    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    return raw_token, expires_at

def decode_access_token(token: str) -> dict:
    """Decode a JWT access token. Raises 401 HTTPException if invalid or expired."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"]
        )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

async def revoke_refresh_token(token_hash: str, db: AsyncSession) -> None:
    """Mark a refresh token as revoked in the database."""
    from app.models.refresh_token import RefreshToken
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    db_token = result.scalar_one_or_none()
    if db_token:
        db_token.revoked = True
        await db.flush()
