"""
User Management API routes.

Provides CRUD operations for users (admin only):
- List/filter users
- Get user details
- Create/update users
- Activate/deactivate users
"""

from typing import Optional
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, EmailStr

from halo.api.deps import User, AdminUser, UserRepo, AuditRepo

router = APIRouter()


# Models
class UserBase(BaseModel):
    """Base user fields."""

    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=100)
    role: str = Field(default="viewer", description="Role: viewer, analyst, senior_analyst, admin")


class UserCreate(UserBase):
    """User creation request."""

    password: str = Field(min_length=8, description="Password must be at least 8 characters")


class UserUpdate(BaseModel):
    """User update request."""

    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    """User response."""

    id: str
    is_active: bool
    last_login: Optional[datetime] = None
    created_at: datetime


class PaginatedUserResponse(BaseModel):
    """Paginated user list response."""

    items: list[UserResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


@router.get("", response_model=PaginatedUserResponse)
async def list_users(
    user: AdminUser,
    user_repo: UserRepo,
    audit_repo: AuditRepo,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    role: Optional[str] = Query(None, description="Filter by role"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
):
    """
    List users with pagination and filtering.

    Requires admin role.
    """
    # Get all users from database
    users = await user_repo.list_users(
        role=role,
        is_active=is_active,
        limit=limit,
        offset=(page - 1) * limit,
    )

    total = await user_repo.count_users(role=role, is_active=is_active)
    total_pages = (total + limit - 1) // limit

    # Log access
    await audit_repo.log(
        user_id=str(user.id),
        action="list_users",
        details={
            "page": page,
            "limit": limit,
            "filters": {"role": role, "is_active": is_active},
        },
    )

    return PaginatedUserResponse(
        items=[
            UserResponse(
                id=str(u.id),
                username=u.username,
                email=u.email,
                full_name=u.full_name,
                role=u.role,
                is_active=u.is_active,
                last_login=u.last_login,
                created_at=u.created_at,
            )
            for u in users
        ],
        total=total,
        page=page,
        page_size=limit,
        total_pages=total_pages,
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    user: AdminUser,
    user_repo: UserRepo,
    audit_repo: AuditRepo,
):
    """
    Get user by ID.

    Requires admin role.
    """
    db_user = await user_repo.get(UUID(user_id))
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Log access
    await audit_repo.log(
        user_id=str(user.id),
        action="get_user",
        entity_id=user_id,
        details={"username": db_user.username},
    )

    return UserResponse(
        id=str(db_user.id),
        username=db_user.username,
        email=db_user.email,
        full_name=db_user.full_name,
        role=db_user.role,
        is_active=db_user.is_active,
        last_login=db_user.last_login,
        created_at=db_user.created_at,
    )


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    data: UserCreate,
    user: AdminUser,
    user_repo: UserRepo,
    audit_repo: AuditRepo,
):
    """
    Create a new user.

    Requires admin role.
    """
    # Check if username already exists
    existing = await user_repo.get_by_username(data.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    # Check if email already exists
    existing = await user_repo.get_by_email(data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    # Create user
    new_user = await user_repo.create(
        username=data.username,
        email=data.email,
        full_name=data.full_name,
        password=data.password,
        role=data.role,
    )

    # Log creation
    await audit_repo.log(
        user_id=str(user.id),
        action="create_user",
        entity_id=str(new_user.id),
        details={
            "username": data.username,
            "role": data.role,
        },
    )

    return UserResponse(
        id=str(new_user.id),
        username=new_user.username,
        email=new_user.email,
        full_name=new_user.full_name,
        role=new_user.role,
        is_active=new_user.is_active,
        last_login=new_user.last_login,
        created_at=new_user.created_at,
    )


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    data: UserUpdate,
    user: AdminUser,
    user_repo: UserRepo,
    audit_repo: AuditRepo,
):
    """
    Update a user.

    Requires admin role.
    """
    db_user = await user_repo.get(UUID(user_id))
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update fields
    updated = await user_repo.update(
        user_id=UUID(user_id),
        email=data.email,
        full_name=data.full_name,
        role=data.role,
        is_active=data.is_active,
    )

    # Log update
    await audit_repo.log(
        user_id=str(user.id),
        action="update_user",
        entity_id=user_id,
        details={
            "username": db_user.username,
            "changes": data.model_dump(exclude_unset=True),
        },
    )

    return UserResponse(
        id=str(updated.id),
        username=updated.username,
        email=updated.email,
        full_name=updated.full_name,
        role=updated.role,
        is_active=updated.is_active,
        last_login=updated.last_login,
        created_at=updated.created_at,
    )


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    user: AdminUser,
    user_repo: UserRepo,
    audit_repo: AuditRepo,
):
    """
    Deactivate a user (soft delete).

    Requires admin role.
    """
    db_user = await user_repo.get(UUID(user_id))
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Deactivate instead of delete
    await user_repo.update(user_id=UUID(user_id), is_active=False)

    # Log deactivation
    await audit_repo.log(
        user_id=str(user.id),
        action="delete_user",
        entity_id=user_id,
        details={"username": db_user.username},
    )
