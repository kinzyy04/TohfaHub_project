import hashlib
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token
from app.services.audit_service import log_event

# Typed exceptions
class EmailAlreadyExists(Exception):
    """Raised when registering an email that already exists in the system."""
    pass

class InvalidCredentials(Exception):
    """Raised when incorrect email or password or inactive account is encountered."""
    pass

class InvalidRefreshToken(Exception):
    """Raised when an unrecognized/invalid refresh token is presented."""
    pass

class RefreshExpired(Exception):
    """Raised when the refresh token's expiration date has passed."""
    pass

class RefreshRevoked(Exception):
    """Raised when the refresh token has already been marked as revoked."""
    pass

async def signup_user(
    db: AsyncSession,
    email: str,
    password: str,
    full_name: str | None = None,
    role: str = "buyer",
    user_agent: str | None = None,
    ip_address: str | None = None
) -> User:
    """Register a new user with a lowercased email, hashed password, and an audit log."""
    email_lower = email.lower().strip()
    
    # Check duplicate
    result = await db.execute(select(User).where(User.email == email_lower))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise EmailAlreadyExists("The user with this email already exists in the system.")
        
    hashed_password = hash_password(password)
    user = User(
        email=email_lower,
        password_hash=hashed_password,
        full_name=full_name,
        role=role,
        is_active=True
    )
    db.add(user)
    await db.flush()
    
    # Write audit log for signup (in the same transaction)
    await log_event(
        db=db,
        event_type="auth.signup",
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent
    )
    await db.flush()
    
    return user

async def login_user(
    db: AsyncSession,
    email: str,
    password: str,
    user_agent: str | None = None,
    ip_address: str | None = None
) -> tuple[User, str, str]:
    """Authenticate user credentials, log success/failure, and issue tokens."""
    email_lower = email.lower().strip()
    
    result = await db.execute(select(User).where(User.email == email_lower))
    user = result.scalar_one_or_none()
    
    if not user:
        # Dummy comparison to mitigate basic timing attacks
        verify_password(password, "$argon2id$v=19$m=65536,t=3,p=2$dummyhashdummyhash")
        
        # Log failure: no_such_user
        await log_event(
            db=db,
            event_type="auth.login.failure",
            user_id=None,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"attempted_email": email_lower, "reason": "no_such_user"}
        )
        await db.commit()  # Ensure failure log is saved in the DB
        raise InvalidCredentials("Incorrect email or password")
        
    if not verify_password(password, user.password_hash):
        # Log failure: wrong_password
        await log_event(
            db=db,
            event_type="auth.login.failure",
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"attempted_email": email_lower, "reason": "wrong_password"}
        )
        await db.commit()  # Ensure failure log is saved in the DB
        raise InvalidCredentials("Incorrect email or password")
        
    if not user.is_active:
        # Log failure: account_disabled
        await log_event(
            db=db,
            event_type="auth.login.failure",
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"attempted_email": email_lower, "reason": "account_disabled"}
        )
        await db.commit()  # Ensure failure log is saved in the DB
        raise InvalidCredentials("User account is inactive")
        
    # Generate tokens
    access_token = create_access_token(user.id, user.role)
    raw_refresh_token, expires_at = create_refresh_token(user.id)
    token_hash = hashlib.sha256(raw_refresh_token.encode()).hexdigest()
    
    # Save the refresh token hash to DB
    db_refresh = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        user_agent=user_agent,
        ip_address=ip_address
    )
    db.add(db_refresh)
    
    # Log success: auth.login.success
    await log_event(
        db=db,
        event_type="auth.login.success",
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent
    )
    await db.flush()
    
    return user, access_token, raw_refresh_token

async def refresh_session(
    db: AsyncSession,
    raw_refresh_token: str,
    user_agent: str | None = None,
    ip_address: str | None = None
) -> tuple[User, str, str]:
    """Verify an existing raw refresh token, revoke it, log the refresh event, and issue a fresh pair."""
    token_hash = hashlib.sha256(raw_refresh_token.encode()).hexdigest()
    
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    db_token = result.scalar_one_or_none()
    
    if not db_token:
        raise InvalidRefreshToken("Invalid refresh token")
        
    if db_token.revoked:
        raise RefreshRevoked("Refresh token has been revoked")
        
    # Expiration check
    if db_token.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise RefreshExpired("Refresh token has expired")
        
    # Retrieve user
    user_result = await db.execute(select(User).where(User.id == db_token.user_id))
    user = user_result.scalar_one_or_none()
    if not user or not user.is_active:
        raise InvalidRefreshToken("User not found or inactive")
        
    # Revoke old refresh token (rotate)
    db_token.revoked = True
    await db.flush()
    
    # Create new tokens
    access_token = create_access_token(user.id, user.role)
    new_raw_refresh, new_expires_at = create_refresh_token(user.id)
    new_hash = hashlib.sha256(new_raw_refresh.encode()).hexdigest()
    
    # Save new refresh token hash
    new_db_refresh = RefreshToken(
        user_id=user.id,
        token_hash=new_hash,
        expires_at=new_expires_at,
        user_agent=user_agent or db_token.user_agent,
        ip_address=ip_address or db_token.ip_address
    )
    db.add(new_db_refresh)
    
    # Log refresh event
    await log_event(
        db=db,
        event_type="auth.refresh",
        user_id=user.id,
        ip_address=ip_address or db_token.ip_address,
        user_agent=user_agent or db_token.user_agent
    )
    await db.flush()
    
    return user, access_token, new_raw_refresh

async def logout(
    db: AsyncSession,
    raw_refresh_token: str,
    user_agent: str | None = None,
    ip_address: str | None = None
) -> None:
    """Revoke a specific refresh token and write a logout audit log."""
    token_hash = hashlib.sha256(raw_refresh_token.encode()).hexdigest()
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    db_token = result.scalar_one_or_none()
    if db_token:
        db_token.revoked = True
        await db.flush()
        
        # Log logout event
        await log_event(
            db=db,
            event_type="auth.logout",
            user_id=db_token.user_id,
            ip_address=ip_address or db_token.ip_address,
            user_agent=user_agent or db_token.user_agent
        )
        await db.flush()
