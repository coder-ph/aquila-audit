from typing import Optional
from fastapi import Header, HTTPException, status
from uuid import UUID

from shared.utils.logging import logger


async def get_tenant_id(
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    tenant_id: Optional[str] = None  # Query parameter
) -> Optional[UUID]:
    """
    Extract tenant ID from headers or query parameters.
    
    Args:
        x_tenant_id: Tenant ID from header
        tenant_id: Tenant ID from query parameter
    
    Returns:
        Tenant ID or None
    """
    tenant_str = x_tenant_id or tenant_id
    
    if not tenant_str:
        return None
    
    try:
        return UUID(tenant_str)
    except ValueError:
        logger.warning(f"Invalid tenant ID format: {tenant_str}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tenant ID format"
        )


async def require_tenant_id(
    tenant_id: Optional[UUID] = Depends(get_tenant_id)
) -> UUID:
    """
    Require tenant ID to be present.
    
    Args:
        tenant_id: Tenant ID
    
    Returns:
        Tenant ID
    
    Raises:
        HTTPException: If tenant ID is missing
    """
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID required. Provide X-Tenant-ID header or tenant_id query parameter"
        )
    
    return tenant_id


async def validate_tenant_access(
    tenant_id: UUID,
    user_tenant_id: Optional[UUID] = None
) -> bool:
    """
    Validate that user has access to tenant.
    
    Args:
        tenant_id: Tenant ID to access
        user_tenant_id: User's tenant ID
    
    Returns:
        True if access is allowed
    """
    # In production, implement proper tenant access validation
    # For now, just check if they match or user is super admin
    
    if user_tenant_id is None:
        # Super admin can access any tenant
        return True
    
    return tenant_id == user_tenant_id


async def get_tenant_context(
    user_info: Optional[tuple] = None,
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID")
) -> tuple[Optional[UUID], Optional[UUID]]:
    """
    Get tenant context for request.
    
    Args:
        user_info: User information tuple (user_id, tenant_id)
        x_tenant_id: Tenant ID from header
    
    Returns:
        Tuple of (user_id, effective_tenant_id)
    """
    user_id = None
    user_tenant_id = None
    
    if user_info:
        user_id, user_tenant_id = user_info
    
    # Determine effective tenant ID
    effective_tenant_id = None
    
    if x_tenant_id:
        try:
            effective_tenant_id = UUID(x_tenant_id)
        except ValueError:
            logger.warning(f"Invalid tenant ID in header: {x_tenant_id}")
    
    # If no header, use user's tenant
    if not effective_tenant_id and user_tenant_id:
        effective_tenant_id = user_tenant_id
    
    # Validate access if both are present
    if effective_tenant_id and user_tenant_id:
        if not await validate_tenant_access(effective_tenant_id, user_tenant_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access to this tenant is not allowed"
            )
    
    return user_id, effective_tenant_id