import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.seller import SellerProfile, SellerPayoutDetails
from app.schemas.seller import (
    SellerStudioProfileResponse,
    SellerProfileUpdateRequest,
    ToggleOrdersResponse,
    PayoutDetailsUpdateRequest,
    PayoutDetailsResponse,
)

router = APIRouter(prefix="/seller", tags=["Seller Studio"])

@router.get("/profile", response_model=SellerStudioProfileResponse)
async def get_seller_profile_studio(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve full profile details for the authenticated seller."""
    result = await db.execute(
        select(SellerProfile).where(SellerProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No seller profile found. Complete onboarding first."
        )

    return profile


@router.patch("/profile", response_model=SellerStudioProfileResponse)
async def update_seller_profile_studio(
    payload: SellerProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Partially update profile details for the authenticated seller."""
    result = await db.execute(
        select(SellerProfile).where(SellerProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No seller profile found. Complete onboarding first."
        )

    update_data = payload.model_dump(exclude_unset=True)

    if "store_handle" in update_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Store handle cannot be changed after creation."
        )

    # Check store name uniqueness if it's changing
    if "store_name" in update_data and update_data["store_name"] != profile.store_name:
        res_name = await db.execute(
            select(SellerProfile).where(
                SellerProfile.store_name == update_data["store_name"],
                SellerProfile.user_id != current_user.id
            )
        )
        if res_name.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Store name is already taken."
            )

    for field, value in update_data.items():
        setattr(profile, field, value)

    profile.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(profile)

    return profile


@router.post("/profile/toggle-orders", response_model=ToggleOrdersResponse)
async def toggle_orders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Flip the is_accepting_orders status of the seller's store."""
    result = await db.execute(
        select(SellerProfile).where(SellerProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No seller profile found. Complete onboarding first."
        )

    profile.is_accepting_orders = not profile.is_accepting_orders
    profile.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(profile)

    if profile.is_accepting_orders:
        message = "Your store is now open ✦"
    else:
        message = "Your store is paused. Buyers cannot place orders."

    return {
        "is_accepting_orders": profile.is_accepting_orders,
        "message": message
    }


@router.patch("/payout-details", response_model=PayoutDetailsResponse)
async def update_payout_details(
    payload: PayoutDetailsUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Partially update payout details for the authenticated seller."""
    result = await db.execute(
        select(SellerProfile)
        .options(selectinload(SellerProfile.payout_details))
        .where(SellerProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No seller profile found. Complete onboarding first."
        )

    payout = profile.payout_details
    if not payout:
        payout = SellerPayoutDetails(
            seller_id=profile.id,
            payout_method="bank",
            pending_payout_amount=0.00
        )
        db.add(payout)
        await db.flush()

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(payout, field, value)

    payout.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(payout)

    return payout
