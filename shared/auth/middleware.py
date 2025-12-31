from typing import Optional, Tuple, Any, Dict
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from uuid import UUID
import json

from shared.auth.jwt_handler import jwt_handler
from shared.utils.logging import logger

class TenantHTTPBearer(HTTPBearer):
    """Custom HTTPBearer that extracts user and tenant info from JWT."""
    
    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error=auto_error)
    
    async def __call__(self, request: Request) -> Optional[HTTPAuthorizationCredentials]:
        credentials = await super().__call__(request)
        
        if credentials:
            payload = jwt_handler.verify_token(credentials.credentials)
            if not payload:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired authentication credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            # Populate request state for downstream dependencies
            try:
                request.state.user_id = UUID(payload.get("sub"))
                # tenant_id can be None for platform admins
                tid = payload.get("tenant_id")
                request.state.tenant_id = UUID(tid) if tid else None
                request.state.scope = payload.get("scope", "user")
                request.state.email = payload.get("email", "unknown@aquila.com")
                request.state.username = payload.get("username", "user")
            except Exception as e:
                logger.error(f"Error parsing JWT payload into state: {str(e)}")
                raise HTTPException(status_code=401, detail="Malformed token payload")
        
        return credentials

# 1. Dependency to get the User object (as expected by your routes)
def get_current_user(request: Request) -> Any:
    """
    Returns an object compatible with the User schema.
    If you have a DB model, you would query it here using request.state.user_id.
    """
    if not hasattr(request.state, 'user_id'):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    # We create a simple Namespace or Class to mimic the User model
    # so that 'current_user.email' works in your routes.
    class UserContext:
        def __init__(self, uid, email, username, scope):
            self.id = uid
            self.email = email
            self.username = username
            self.is_admin = (scope == "admin")
            self.scope = scope

    return UserContext(
        uid=request.state.user_id,
        email=getattr(request.state, 'email', None),
        username=getattr(request.state, 'username', None),
        scope=getattr(request.state, 'scope', 'user')
    )

# 2. Dependency to verify and return tenant_id (as expected by your routes)
async def verify_tenant_access(request: Request) -> str:
    """
    Ensures a tenant context exists and returns the ID as a string.
    """
    if not hasattr(request.state, 'tenant_id') or request.state.tenant_id is None:
        # Check headers if state is empty (fallback for non-JWT flows)
        tenant_header = request.headers.get("X-Tenant-ID")
        if tenant_header:
            try:
                return str(UUID(tenant_header))
            except ValueError:
                pass
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context is required for this operation"
        )
    
    return str(request.state.tenant_id)

# 3. Helper for generic tenant requirement (returns UUID)
def tenant_required(request: Request) -> UUID:
    """Ensures tenant context is present and returns it as a UUID."""
    if not hasattr(request.state, 'tenant_id') or not request.state.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required"
        )
    return request.state.tenant_id

class TenantMiddleware:
    """ASGI Middleware for manual tenant extraction from headers/params."""
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        request = Request(scope, receive)
        if not hasattr(request.state, 'tenant_id'):
            t_id = request.headers.get("X-Tenant-ID") or request.query_params.get("tenant_id")
            if t_id:
                try:
                    request.state.tenant_id = UUID(t_id)
                except (ValueError, TypeError):
                    pass
        
        await self.app(scope, receive, send)

# Security scheme for FastAPI docs
security_scheme = TenantHTTPBearer()