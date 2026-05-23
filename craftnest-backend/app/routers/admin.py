from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import require_admin
from app.models.user import User
from app.utils.request_meta import extract_request_meta
from app.services.audit_service import log_event
from app.services import admin_service

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])

@router.get("/stats")
async def get_admin_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    # Audit log: event_type='admin.stats.viewed'
    ip_address, user_agent = extract_request_meta(request)
    await log_event(
        db=db,
        event_type="admin.stats.viewed",
        user_id=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.flush()
    
    return await admin_service.get_admin_stats(db)

