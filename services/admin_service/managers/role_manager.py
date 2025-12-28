from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from uuid import UUID
import json

from shared.database.session import get_session
from shared.models.user_models import UserRole, User, Tenant
from shared.utils.logging import logger

from services.admin_service.dependencies.auth import verify_admin_token

# Create router
router = APIRouter(dependencies=[Depends(verify_admin_token)])


@router.post("/")
async def create_user_role(
    user_id: UUID,
    tenant_id: UUID,
    role: str,
    permissions: Optional[List[str]] = None,
    db: Session = Depends(get_session)
):
    """
    Create a user role.
    """
    # Check if user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Check if tenant exists
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    # Check if role already exists
    existing_role = db.query(UserRole).filter(
        UserRole.user_id == user_id,
        UserRole.tenant_id == tenant_id,
        UserRole.role == role
    ).first()
    
    if existing_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role '{role}' already exists for this user in tenant"
        )
    
    # Create role
    db_role = UserRole(
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
        permissions=json.dumps(permissions) if permissions else None
    )
    
    db.add(db_role)
    db.commit()
    db.refresh(db_role)
    
    logger.info(f"Role created: {role} for user {user.email} in tenant {tenant.slug}")
    
    return {
        "role_id": str(db_role.id),
        "user_id": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "permissions": permissions or []
    }


@router.get("/")
async def list_user_roles(
    user_id: Optional[UUID] = None,
    tenant_id: Optional[UUID] = None,
    role: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_session)
):
    """
    List user roles.
    """
    # Build query
    query = db.query(UserRole)
    
    # Apply filters
    if user_id:
        query = query.filter(UserRole.user_id == user_id)
    
    if tenant_id:
        query = query.filter(UserRole.tenant_id == tenant_id)
    
    if role:
        query = query.filter(UserRole.role == role)
    
    # Get total count
    total = query.count()
    
    # Get paginated results
    roles = query.order_by(UserRole.created_at.desc()).offset(skip).limit(limit).all()
    
    # Format response
    role_data = []
    for role_obj in roles:
        role_data.append({
            "role_id": str(role_obj.id),
            "user_id": str(role_obj.user_id),
            "tenant_id": str(role_obj.tenant_id),
            "role": role_obj.role,
            "permissions": role_obj.permission_list,
            "created_at": role_obj.created_at.isoformat() if role_obj.created_at else None
        })
    
    return {
        "items": role_data,
        "total": total,
        "page": skip // limit + 1,
        "page_size": limit,
        "total_pages": (total + limit - 1) // limit
    }


@router.get("/{role_id}")
async def get_user_role(
    role_id: UUID,
    db: Session = Depends(get_session)
):
    """
    Get user role details.
    """
    role = db.query(UserRole).filter(UserRole.id == role_id).first()
    
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    
    # Get user and tenant info
    user = db.query(User).filter(User.id == role.user_id).first()
    tenant = db.query(Tenant).filter(Tenant.id == role.tenant_id).first()
    
    return {
        "role_id": str(role.id),
        "user_id": str(role.user_id),
        "tenant_id": str(role.tenant_id),
        "user_email": user.email if user else None,
        "tenant_name": tenant.name if tenant else None,
        "role": role.role,
        "permissions": role.permission_list,
        "created_at": role.created_at.isoformat() if role.created_at else None,
        "updated_at": role.updated_at.isoformat() if role.updated_at else None
    }


@router.put("/{role_id}")
async def update_user_role(
    role_id: UUID,
    role: Optional[str] = None,
    permissions: Optional[List[str]] = None,
    db: Session = Depends(get_session)
):
    """
    Update user role.
    """
    db_role = db.query(UserRole).filter(UserRole.id == role_id).first()
    
    if not db_role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    
    # Update fields
    if role:
        db_role.role = role
    
    if permissions is not None:
        db_role.permissions = json.dumps(permissions) if permissions else None
    
    db.commit()
    db.refresh(db_role)
    
    logger.info(f"Role updated: {db_role.id}")
    
    return {
        "role_id": str(db_role.id),
        "role": db_role.role,
        "permissions": db_role.permission_list
    }


@router.delete("/{role_id}")
async def delete_user_role(
    role_id: UUID,
    db: Session = Depends(get_session)
):
    """
    Delete a user role.
    """
    role = db.query(UserRole).filter(UserRole.id == role_id).first()
    
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    
    db.delete(role)
    db.commit()
    
    logger.warning(f"Role deleted: {role_id}")
    
    return {"message": "Role deleted successfully"}


@router.get("/permissions/all")
async def get_all_permissions():
    """
    Get all available permissions.
    """
    from shared.auth.rbac import Permission
    
    return {
        "permissions": [permission.value for permission in Permission]
    }