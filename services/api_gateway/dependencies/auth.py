from typing import Optional, Tuple

from fastapi.security import HTTPBearer
from uuid import UUID
from fastapi import Header, HTTPException, status, Depends

from services.admin_service.config import config
from shared.utils.logging import logger

from shared.auth.jwt_handler import jwt_handler
from shared.auth.middleware import TenantHTTPBearer
from shared.utils.logging import logger


security = TenantHTTPBearer()


async def get_current_user(
    credentials: HTTPBearer = Depends(security)
) -> Tuple[UUID, Optional[UUID]]:
    """
    Get current user from JWT token.
    
    Args:
        credentials: HTTP bearer credentials
    
    Returns:
        Tuple of (user_id, tenant_id)
    
    Raises:
        HTTPException: If token is invalid
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials missing"
        )
    
    # Verify token
    payload = jwt_handler.verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extract user info
    try:
        user_id = UUID(payload.get("sub"))
        tenant_id = UUID(payload.get("tenant_id")) if payload.get("tenant_id") else None
        
        logger.debug(
            "User authenticated",
            user_id=str(user_id),
            tenant_id=str(tenant_id) if tenant_id else None
        )
        
        return user_id, tenant_id
    
    except (ValueError, TypeError) as e:
        logger.error(f"Invalid token payload: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )


async def get_current_user_with_tenant(
    user_info: Tuple[UUID, Optional[UUID]] = Depends(get_current_user)
) -> Tuple[UUID, UUID]:
    """
    Get current user with tenant context.
    
    Args:
        user_info: User information tuple
    
    Returns:
        Tuple of (user_id, tenant_id)
    
    Raises:
        HTTPException: If tenant context is missing
    """
    user_id, tenant_id = user_info
    
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required"
        )
    
    return user_id, tenant_id


async def require_admin(
    user_info: Tuple[UUID, Optional[UUID]] = Depends(get_current_user)
) -> Tuple[UUID, UUID]:
    """
    Require admin privileges.
    
    Args:
        user_info: User information tuple
    
    Returns:
        Tuple of (user_id, tenant_id)
    
    Raises:
        HTTPException: If not admin
    """
    user_id, tenant_id = user_info
    
    # In production, you would check user role in database
    # For now, we'll accept any authenticated user with tenant context
    
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access requires tenant context"
        )
    
    return user_id, tenant_id


async def optional_auth(
    credentials: Optional[HTTPBearer] = Depends(security, use_cache=False)
) -> Optional[Tuple[UUID, Optional[UUID]]]:
    """
    Optional authentication.
    
    Args:
        credentials: Optional HTTP bearer credentials
    
    Returns:
        User info if authenticated, None otherwise
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None
    
async def verify_admin_token(
    x_admin_token: str = Header(None, alias="X-Admin-Token")
):
    """
    Verify admin token for admin service endpoints.
    
    Args:
        x_admin_token: Admin token from header
    
    Raises:
        HTTPException: If token is invalid
    """
    if not config.require_admin_token:
        return
    
    if not x_admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin token required"
        )
    
    if x_admin_token != config.admin_token:
        logger.warning("Invalid admin token attempt")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin token"
        )