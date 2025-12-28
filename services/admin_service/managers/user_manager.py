from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from uuid import UUID

from shared.database.session import get_session
from shared.models.schemas import (
    UserCreate,
    UserUpdate,
    UserResponse,
    PaginatedResponse
)
from shared.models.user_models import User, Tenant, UserTenant
from shared.auth.password import PasswordManager, get_password_hash
from shared.utils.logging import logger

from services.admin_service.dependencies.auth import verify_admin_token

# Create router
router = APIRouter(dependencies=[Depends(verify_admin_token)])


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user: UserCreate,
    db: Session = Depends(get_session)
):
    """
    Create a new user.
    """
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with email '{user.email}' already exists"
        )
    
    # Hash password
    hashed_password = get_password_hash(user.password)
    
    # Create user
    db_user = User(
        email=user.email,
        hashed_password=hashed_password,
        full_name=user.full_name,
        company=user.company,
        phone=user.phone,
        is_active=True,
        is_verified=True,
        is_superuser=False
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    logger.info(f"User created: {user.email}")
    
    return db_user


@router.get("/", response_model=PaginatedResponse)
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    is_active: Optional[bool] = None,
    is_verified: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_session)
):
    """
    List all users.
    """
    # Build query
    query = db.query(User)
    
    # Apply filters
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    
    if is_verified is not None:
        query = query.filter(User.is_verified == is_verified)
    
    if search:
        query = query.filter(
            (User.email.ilike(f"%{search}%")) | 
            (User.full_name.ilike(f"%{search}%")) |
            (User.company.ilike(f"%{search}%"))
        )
    
    # Get total count
    total = query.count()
    
    # Get paginated results
    users = query.order_by(User.created_at.desc()).offset(skip).limit(limit).all()
    
    return {
        "items": users,
        "total": total,
        "page": skip // limit + 1,
        "page_size": limit,
        "total_pages": (total + limit - 1) // limit
    }


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    db: Session = Depends(get_session)
):
    """
    Get user details.
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    user_update: UserUpdate,
    db: Session = Depends(get_session)
):
    """
    Update user.
    """
    db_user = db.query(User).filter(User.id == user_id).first()
    
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update fields
    update_data = user_update.dict(exclude_unset=True)
    
    for field, value in update_data.items():
        if hasattr(db_user, field):
            setattr(db_user, field, value)
    
    db.commit()
    db.refresh(db_user)
    
    logger.info(f"User updated: {db_user.email}")
    
    return db_user


@router.delete("/{user_id}")
async def delete_user(
    user_id: UUID,
    force: bool = Query(False, description="Force delete even if user has data"),
    db: Session = Depends(get_session)
):
    """
    Delete a user.
    """
    db_user = db.query(User).filter(User.id == user_id).first()
    
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Check if user has tenants
    if not force and db_user.tenants:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete user with tenants. Use force=true to delete anyway."
        )
    
    # Delete user
    db.delete(db_user)
    db.commit()
    
    logger.warning(f"User deleted: {db_user.email}")
    
    return {"message": "User deleted successfully"}


@router.post("/{user_id}/reset-password")
async def reset_user_password(
    user_id: UUID,
    new_password: str,
    db: Session = Depends(get_session)
):
    """
    Reset user password.
    """
    db_user = db.query(User).filter(User.id == user_id).first()
    
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Validate password strength
    is_valid, errors = PasswordManager.validate_password_strength(new_password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password validation failed: {', '.join(errors)}"
        )
    
    # Update password
    db_user.hashed_password = get_password_hash(new_password)
    db_user.password_changed_at = datetime.utcnow()
    db.commit()
    
    logger.info(f"Password reset for user: {db_user.email}")
    
    return {"message": "Password reset successfully"}


@router.get("/{user_id}/tenants")
async def get_user_tenants(
    user_id: UUID,
    db: Session = Depends(get_session)
):
    """
    Get tenants for a user.
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Get user's tenants with roles
    user_tenants = []
    for tenant in user.tenants:
        # Get the role from user_tenants table
        user_tenant = db.query(UserTenant).filter(
            UserTenant.user_id == user_id,
            UserTenant.tenant_id == tenant.id
        ).first()
        
        user_tenants.append({
            "tenant_id": str(tenant.id),
            "name": tenant.name,
            "slug": tenant.slug,
            "role": user_tenant.role if user_tenant else None,
            "joined_at": user_tenant.joined_at if user_tenant else None
        })
    
    return {"user_id": str(user_id), "tenants": user_tenants}