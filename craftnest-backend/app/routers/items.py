from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.core.database import get_db
from app.models.item import Item
from app.models.user import User
from app.schemas.item import ItemCreate, ItemResponse
from app.routers.deps import get_current_user, RoleChecker
from app.core.rate_limit import rate_limit_by_user

router = APIRouter(prefix="/api/v1/items", tags=["Items"])

@router.post("", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
@rate_limit_by_user("120/minute")
async def create_item(
    request: Request,
    item_in: ItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RoleChecker(["seller", "admin"]))
):
    if item_in.price <= 0:
        raise HTTPException(
            status_code=422,
            detail="Price must be greater than zero",
        )
    
    db_item = Item(
        name=item_in.name,
        description=item_in.description,
        price=item_in.price,
        owner_id=current_user.id
    )
    db.add(db_item)
    await db.flush()
    return db_item

@router.get("/{item_id}", response_model=ItemResponse)
@rate_limit_by_user("120/minute")
async def read_item(
    request: Request,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@router.put("/{item_id}", response_model=ItemResponse)
@rate_limit_by_user("120/minute")
async def update_item(
    request: Request,
    item_id: int,
    item_in: ItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    if item.owner_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Not enough permissions to access this resource",
        )
        
    item.name = item_in.name
    item.description = item_in.description
    item.price = item_in.price
    await db.flush()
    return item

@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
@rate_limit_by_user("120/minute")
async def delete_item(
    request: Request,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
        
    if item.owner_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Not enough permissions to access this resource",
        )
        
    await db.delete(item)
    await db.flush()

