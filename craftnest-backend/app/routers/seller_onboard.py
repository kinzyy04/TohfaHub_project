import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import delete

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.seller import SellerProfile, SellerOnboardingStatus, SellerPayoutDetails
from app.schemas.seller import (
    BecomeSellerRequest,
    BecomeSellerResponse,
    SellerStudioShellResponse,
    OnboardingStepResponse
)

router = APIRouter(prefix="/seller", tags=["Seller Onboarding"])

STEPS = [
    "store_details", "payment_gateway", "shipping", "store_policies",
    "website_appearance", "user_access", "accept_orders", "gift_wrap"
]

@router.post("/become-a-seller", response_model=BecomeSellerResponse, status_code=status.HTTP_201_CREATED)
async def become_a_seller(
    payload: BecomeSellerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Transition user to seller role and initialize their onboarding steps."""
    # Check if store_name is already taken by another profile
    res_name = await db.execute(
        select(SellerProfile).where(
            SellerProfile.store_name == payload.store_name,
            SellerProfile.user_id != current_user.id
        )
    )
    if res_name.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Store name is already taken."
        )

    # Check if store_handle is already taken by another profile
    res_handle = await db.execute(
        select(SellerProfile).where(
            SellerProfile.store_handle == payload.store_handle,
            SellerProfile.user_id != current_user.id
        )
    )
    if res_handle.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Store handle is already taken."
        )

    # Check if profile already exists for the user
    res_profile = await db.execute(
        select(SellerProfile).where(SellerProfile.user_id == current_user.id)
    )
    profile = res_profile.scalar_one_or_none()

    if not profile:
        profile = SellerProfile(
            user_id=current_user.id,
            store_name=payload.store_name,
            store_handle=payload.store_handle,
            bio=payload.bio
        )
        db.add(profile)
        await db.flush()
    else:
        profile.store_name = payload.store_name
        profile.store_handle = payload.store_handle
        if payload.bio is not None:
            profile.bio = payload.bio
        await db.flush()

    # Clean delete any existing steps or payout details to prevent duplicates
    await db.execute(
        delete(SellerOnboardingStatus).where(SellerOnboardingStatus.seller_id == profile.id)
    )
    await db.execute(
        delete(SellerPayoutDetails).where(SellerPayoutDetails.seller_id == profile.id)
    )

    # Seed all 8 onboarding status rows
    for step in STEPS:
        db.add(SellerOnboardingStatus(
            seller_id=profile.id,
            step_key=step,
            is_complete=False,
            completed_at=None
        ))

    # Seed empty payout details
    db.add(SellerPayoutDetails(
        seller_id=profile.id,
        payout_method="bank",
        pending_payout_amount=0.00
    ))

    # Ensure user has the seller role
    if current_user.role != "seller":
        current_user.role = "seller"

    await db.flush()

    # Load profile with relationship populated for serialization
    result = await db.execute(
        select(SellerProfile)
        .options(selectinload(SellerProfile.onboarding_status))
        .where(SellerProfile.id == profile.id)
    )
    profile = result.scalar_one()
    
    return profile


@router.get("/studio/shell", response_model=SellerStudioShellResponse)
async def get_studio_shell(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve overview details for the Seller Studio Shell."""
    result = await db.execute(
        select(SellerProfile)
        .options(
            selectinload(SellerProfile.onboarding_status),
            selectinload(SellerProfile.payout_details)
        )
        .where(SellerProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile or not profile.onboarding_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No seller profile found. Complete onboarding first."
        )

    complete_count = sum(1 for step in profile.onboarding_status if step.is_complete)
    total_count = len(profile.onboarding_status)

    return {
        "store_name": profile.store_name,
        "store_handle": profile.store_handle,
        "avatar_url": profile.avatar_url,
        "is_accepting_orders": profile.is_accepting_orders,
        "pending_payout_amount": profile.payout_details.pending_payout_amount if profile.payout_details else 0.0,
        "payout_schedule": profile.payout_details.payout_schedule if profile.payout_details else "Every Monday 10 AM",
        "onboarding_progress": {
            "complete": complete_count,
            "total": total_count
        }
    }


@router.patch("/onboarding/step/{step_key}", response_model=list[OnboardingStepResponse])
async def complete_onboarding_step(
    step_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark a specific onboarding step as complete."""
    if step_key not in STEPS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid step key '{step_key}'. Valid step keys are: {', '.join(sorted(STEPS))}"
        )

    result = await db.execute(
        select(SellerProfile)
        .options(selectinload(SellerProfile.onboarding_status))
        .where(SellerProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile or not profile.onboarding_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No seller profile found. Complete onboarding first."
        )

    target_step = None
    for step in profile.onboarding_status:
        if step.step_key == step_key:
            target_step = step
            break

    if target_step:
        target_step.is_complete = True
        target_step.completed_at = datetime.now(timezone.utc)
        await db.flush()

    # Return updated sorted steps
    return sorted(profile.onboarding_status, key=lambda x: x.step_key)
