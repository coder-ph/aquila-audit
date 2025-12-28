from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from uuid import UUID

from shared.database.session import get_session
from shared.models.schemas import (
    TenantCreate, 
    TenantUpdate, 
    TenantResponse,
    PaginatedResponse
)
from shared.models.user_models import Tenant, UserTenant
from shared.utils.logging import logger

from services.admin_service.dependencies.auth import verify_admin_token

# Create router
router = APIRouter(dependencies=[Depends(verify_admin_token)])


@router.post("/", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    tenant: TenantCreate,
    owner_user_id: Optional[UUID] = None,
    db: Session = Depends(get_session)
):
    """
    Create a new tenant.
    """
    # Check if tenant slug already exists
    existing_tenant = db.query(Tenant).filter(Tenant.slug == tenant.slug).first()
    if existing_tenant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tenant with slug '{tenant.slug}' already exists"
        )
    
    # Create tenant
    db_tenant = Tenant(
        name=tenant.name,
        slug=tenant.slug,
        description=tenant.description,
        config=tenant.config or {},
        billing_tier="free"
    )
    
    db.add(db_tenant)
    db.commit()
    db.refresh(db_tenant)
    
    logger.info(f"Tenant created: {tenant.slug}")
    
    return db_tenant


@router.get("/", response_model=PaginatedResponse)
async def list_tenants(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_session)
):
    """
    List all tenants.
    """
    # Build query
    query = db.query(Tenant)
    
    # Apply filters
    if is_active is not None:
        query = query.filter(Tenant.is_active == is_active)
    
    if search:
        query = query.filter(
            (Tenant.name.ilike(f"%{search}%")) | 
            (Tenant.slug.ilike(f"%{search}%")) |
            (Tenant.description.ilike(f"%{search}%"))
        )
    
    # Get total count
    total = query.count()
    
    # Get paginated results
    tenants = query.order_by(Tenant.created_at.desc()).offset(skip).limit(limit).all()
    
    # Add user count to each tenant
    for tenant in tenants:
        tenant.user_count = len(tenant.users)
    
    return {
        "items": tenants,
        "total": total,
        "page": skip // limit + 1,
        "page_size": limit,
        "total_pages": (total + limit - 1) // limit
    }


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: UUID,
    db: Session = Depends(get_session)
):
    """
    Get tenant details.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    # Add user count
    tenant.user_count = len(tenant.users)
    
    return tenant


@router.put("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: UUID,
    tenant_update: TenantUpdate,
    db: Session = Depends(get_session)
):
    """
    Update tenant.
    """
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    
    if not db_tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    # Update fields
    update_data = tenant_update.dict(exclude_unset=True)
    
    for field, value in update_data.items():
        if hasattr(db_tenant, field):
            setattr(db_tenant, field, value)
    
    db.commit()
    db.refresh(db_tenant)
    
    logger.info(f"Tenant updated: {db_tenant.slug}")
    
    return db_tenant


@router.delete("/{tenant_id}")
async def delete_tenant(
    tenant_id: UUID,
    force: bool = Query(False, description="Force delete even if tenant has data"),
    db: Session = Depends(get_session)
):
    """
    Delete a tenant.
    
    By default, only empty tenants can be deleted.
    Use force=True to delete tenants with data.
    """
    db_tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    
    if not db_tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    # Check if tenant has data
    if not force:
        # Check for users
        if db_tenant.users:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete tenant with users. Use force=true to delete anyway."
            )
        
        # Check for files, rules, etc. (simplified check)
        # In production, you would check all related tables
    
    # Delete tenant
    db.delete(db_tenant)
    db.commit()
    
    logger.warning(f"Tenant deleted: {db_tenant.slug}")
    
    return {"message": "Tenant deleted successfully"}


@router.post("/{tenant_id}/users/{user_id}")
async def add_user_to_tenant(
    tenant_id: UUID,
    user_id: UUID,
    role: str = Query("member", description="User role in tenant"),
    db: Session = Depends(get_session)
):
    """
    Add user to tenant.
    """
    # Check if tenant exists
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    # Check if user exists
    from shared.models.user_models import User
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Check if user is already in tenant
    existing_assoc = db.query(UserTenant).filter(
        UserTenant.user_id == user_id,
        UserTenant.tenant_id == tenant_id
    ).first()
    
    if existing_assoc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already in tenant"
        )
    
    # Add user to tenant
    user_tenant = UserTenant(
        user_id=user_id,
        tenant_id=tenant_id,
        role=role
    )
    
    db.add(user_tenant)
    db.commit()
    
    logger.info(f"User added to tenant: {user.email} -> {tenant.slug}")
    
    return {"message": "User added to tenant successfully"}


@router.delete("/{tenant_id}/users/{user_id}")
async def remove_user_from_tenant(
    tenant_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_session)
):
    """
    Remove user from tenant.
    """
    # Check if association exists
    user_tenant = db.query(UserTenant).filter(
        UserTenant.user_id == user_id,
        UserTenant.tenant_id == tenant_id
    ).first()
    
    if not user_tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in tenant"
        )
    
    # Remove association
    db.delete(user_tenant)
    db.commit()
    
    logger.info(f"User removed from tenant: {user_id} -> {tenant_id}")
    
    return {"message": "User removed from tenant successfully"}


@router.get("/{tenant_id}/users")
async def list_tenant_users(
    tenant_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_session)
):
    """
    List users in a tenant.
    """
    # Check if tenant exists
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    # Get users with their roles
    from shared.models.user_models import User
    
    users = db.query(User).join(UserTenant).filter(
        UserTenant.tenant_id == tenant_id
    ).offset(skip).limit(limit).all()
    
    # Get user roles
    user_data = []
    for user in users:
        assoc = db.query(UserTenant).filter(
            UserTenant.user_id == user.id,
            UserTenant.tenant_id == tenant_id
        ).first()
        
        user_data.append({
            "user_id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": assoc.role if assoc else None,
            "joined_at": assoc.joined_at if assoc else None,
            "is_active": user.is_active
        })
    
    total = db.query(User).join(UserTenant).filter(
        UserTenant.tenant_id == tenant_id
    ).count()
    
    return {
        "items": user_data,
        "total": total,
        "page": skip // limit + 1,
        "page_size": limit,
        "total_pages": (total + limit - 1) // limit
    }