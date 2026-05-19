from fastapi import Depends, HTTPException, status
from app.core.deps import get_current_user
from app.models.user import User

class RoleChecker:
    """Dependency that checks if the current authenticated user has an authorized role."""
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, user: User = Depends(get_current_user)) -> User:
        if user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted for this role",
            )
        return user
