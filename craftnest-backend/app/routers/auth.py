import hashlib
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import create_access_token, create_refresh_token
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.schemas.auth import SignupRequest, LoginRequest, RefreshRequest, AuthResponse
from app.schemas.user import UserResponse
from app.utils.request_meta import extract_request_meta
from app.core.rate_limit import limiter, rate_limit_by_user
from app.services.auth_service import (
    signup_user,
    login_user,
    refresh_session,
    logout,
    EmailAlreadyExists,
    InvalidCredentials,
    InvalidRefreshToken,
    RefreshExpired,
    RefreshRevoked,
)

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

@router.post(
    "/signup",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
@limiter.limit("3/minute")
async def signup(
    request_data: SignupRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Registers a new user and issues access + refresh tokens immediately (auto-login)."""
    try:
        ip_address, user_agent = extract_request_meta(request)
        user = await signup_user(
            db=db,
            email=request_data.email,
            password=request_data.password,
            full_name=request_data.full_name,
            role=request_data.role,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        # Issue tokens directly
        access_token = create_access_token(user.id, user.role)
        raw_refresh, expires_at = create_refresh_token(user.id)
        refresh_hash = hashlib.sha256(raw_refresh.encode()).hexdigest()
        
        db_refresh = RefreshToken(
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        db.add(db_refresh)
        await db.flush()
        
        return {
            "access_token": access_token,
            "refresh_token": raw_refresh,
            "user_id": user.id,
            "role": user.role,
        }
    except EmailAlreadyExists as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

@router.post(
    "/login",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    summary="Login to obtain tokens",
)
@limiter.limit("5/minute")
async def login(
    request_data: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Authenticates credentials and returns access + refresh tokens."""
    try:
        ip_address, user_agent = extract_request_meta(request)
        user, access_token, raw_refresh = await login_user(
            db=db,
            email=request_data.email,
            password=request_data.password,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        return {
            "access_token": access_token,
            "refresh_token": raw_refresh,
            "user_id": user.id,
            "role": user.role,
        }
    except InvalidCredentials as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

@router.post(
    "/refresh",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
)
@limiter.limit("30/minute")
async def refresh(
    request_data: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Revokes the current refresh token and issues a new access + refresh token pair."""
    try:
        ip_address, user_agent = extract_request_meta(request)
        user, access_token, raw_refresh = await refresh_session(
            db=db,
            raw_refresh_token=request_data.refresh_token,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        return {
            "access_token": access_token,
            "refresh_token": raw_refresh,
            "user_id": user.id,
            "role": user.role,
        }
    except (InvalidRefreshToken, RefreshExpired, RefreshRevoked) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )

@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Revoke access session",
)
@rate_limit_by_user("120/minute")
async def logout_endpoint(
    request_data: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Invalidates the provided refresh token. Requires access token authorization."""
    ip_address, user_agent = extract_request_meta(request)
    await logout(
        db=db,
        raw_refresh_token=request_data.refresh_token,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return {"detail": "Successfully logged out"}

@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current user details",
)
@rate_limit_by_user("120/minute")
async def get_me(request: Request, current_user: User = Depends(get_current_user)):
    """Returns the details of the currently authenticated user."""
    return current_user

