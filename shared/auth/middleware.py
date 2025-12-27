from typing import Optional, Tuple
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from uuid import UUID

from shared.database.session import get_session
from shared.auth.jwt_handler import jwt_handler
from shared.utils.logging import logger


class TenantHTTPBearer(HTTPBearer):
    """Custom HTTPBearer with tenant support."""
    
    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error=auto_error)
    
    async def __call__(self, request: Request) -> Optional[HTTPAuthorizationCredentials]:
        credentials = await super().__call__(request)
        
        if credentials:
            # Verify token
            payload = jwt_handler.verify_token(credentials.credentials)
            if not payload:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            # Add user info to request state
            request.state.user_id = UUID(payload.get("sub"))
            request.state.tenant_id = UUID(payload.get("tenant_id")) if payload.get("tenant_id") else None
            request.state.scope = payload.get("scope", "user")
        
        return credentials


def get_current_user(
    request: Request,
    required_scope: Optional[str] = None
) -> Tuple[UUID, Optional[UUID]]:
    """
    Get current user from request.
    
    Args:
        request: FastAPI request
        required_scope: Required scope for authorization
    
    Returns:
        Tuple of (user_id, tenant_id)
    
    Raises:
        HTTPException: If user not authenticated or scope insufficient
    """
    if not hasattr(request.state, 'user_id'):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    # Check scope if required
    if required_scope and hasattr(request.state, 'scope'):
        if request.state.scope != required_scope:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required scope: {required_scope}"
            )
    
    return request.state.user_id, request.state.tenant_id


def tenant_required(request: Request) -> UUID:
    """
    Ensure tenant context is present.
    
    Args:
        request: FastAPI request
    
    Returns:
        Tenant ID
    
    Raises:
        HTTPException: If tenant not in context
    """
    user_id, tenant_id = get_current_user(request)
    
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required"
        )
    
    return tenant_id


class TenantMiddleware:
    """Middleware for tenant isolation."""
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        request = Request(scope, receive)
        
        # Extract tenant from headers or query params for non-auth routes
        if not hasattr(request.state, 'tenant_id'):
            tenant_header = request.headers.get("X-Tenant-ID")
            tenant_query = request.query_params.get("tenant_id")
            
            if tenant_header:
                try:
                    request.state.tenant_id = UUID(tenant_header)
                except ValueError:
                    pass
            elif tenant_query:
                try:
                    request.state.tenant_id = UUID(tenant_query)
                except ValueError:
                    pass
        
        await self.app(scope, receive, send)


# Security scheme for OpenAPI
security_scheme = TenantHTTPBearer()