from enum import Enum
from typing import List, Set, Optional
from functools import wraps
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from shared.utils.logging import logger


class Permission(str, Enum):
    """System permissions."""
    
    # User permissions
    USER_READ = "user:read"
    USER_WRITE = "user:write"
    USER_DELETE = "user:delete"
    
    # File permissions
    FILE_UPLOAD = "file:upload"
    FILE_READ = "file:read"
    FILE_DELETE = "file:delete"
    
    # Rule permissions
    RULE_READ = "rule:read"
    RULE_WRITE = "rule:write"
    RULE_DELETE = "rule:delete"
    
    # Report permissions
    REPORT_GENERATE = "report:generate"
    REPORT_READ = "report:read"
    REPORT_DELETE = "report:delete"
    
    # Admin permissions
    ADMIN_READ = "admin:read"
    ADMIN_WRITE = "admin:write"
    ADMIN_DELETE = "admin:delete"


class Role(str, Enum):
    """System roles with associated permissions."""
    
    SUPER_ADMIN = "super_admin"
    TENANT_ADMIN = "tenant_admin"
    AUDITOR = "auditor"
    VIEWER = "viewer"
    ANALYST = "analyst"


# Role to permission mapping
ROLE_PERMISSIONS = {
    Role.SUPER_ADMIN: {
        Permission.USER_READ,
        Permission.USER_WRITE,
        Permission.USER_DELETE,
        Permission.FILE_UPLOAD,
        Permission.FILE_READ,
        Permission.FILE_DELETE,
        Permission.RULE_READ,
        Permission.RULE_WRITE,
        Permission.RULE_DELETE,
        Permission.REPORT_GENERATE,
        Permission.REPORT_READ,
        Permission.REPORT_DELETE,
        Permission.ADMIN_READ,
        Permission.ADMIN_WRITE,
        Permission.ADMIN_DELETE,
    },
    Role.TENANT_ADMIN: {
        Permission.USER_READ,
        Permission.USER_WRITE,
        Permission.USER_DELETE,
        Permission.FILE_UPLOAD,
        Permission.FILE_READ,
        Permission.FILE_DELETE,
        Permission.RULE_READ,
        Permission.RULE_WRITE,
        Permission.RULE_DELETE,
        Permission.REPORT_GENERATE,
        Permission.REPORT_READ,
        Permission.REPORT_DELETE,
    },
    Role.AUDITOR: {
        Permission.FILE_UPLOAD,
        Permission.FILE_READ,
        Permission.RULE_READ,
        Permission.REPORT_GENERATE,
        Permission.REPORT_READ,
    },
    Role.ANALYST: {
        Permission.FILE_READ,
        Permission.RULE_READ,
        Permission.REPORT_READ,
    },
    Role.VIEWER: {
        Permission.FILE_READ,
        Permission.REPORT_READ,
    },
}


class RBACManager:
    """Role-Based Access Control manager."""
    
    @staticmethod
    def get_permissions_for_role(role: Role) -> Set[Permission]:
        """
        Get permissions for a role.
        
        Args:
            role: User role
        
        Returns:
            Set of permissions
        """
        return ROLE_PERMISSIONS.get(role, set())
    
    @staticmethod
    def has_permission(role: Role, permission: Permission) -> bool:
        """
        Check if role has specific permission.
        
        Args:
            role: User role
            permission: Permission to check
        
        Returns:
            True if role has permission
        """
        return permission in ROLE_PERMISSIONS.get(role, set())
    
    @staticmethod
    def check_permission(
        user_permissions: Set[Permission],
        required_permission: Permission
    ) -> bool:
        """
        Check if user has required permission.
        
        Args:
            user_permissions: User's permissions
            required_permission: Required permission
        
        Returns:
            True if user has permission
        """
        return required_permission in user_permissions
    
    @staticmethod
    def get_all_permissions() -> List[Permission]:
        """Get all available permissions."""
        return list(Permission)


def permission_required(permission: Permission):
    """
    Decorator to check permissions.
    
    Args:
        permission: Required permission
    
    Returns:
        Decorated function
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from args or kwargs
            request = None
            for arg in args:
                if hasattr(arg, 'state') and hasattr(arg.state, 'scope'):
                    request = arg
                    break
            
            if not request:
                for key, value in kwargs.items():
                    if hasattr(value, 'state') and hasattr(value.state, 'scope'):
                        request = value
                        break
            
            if not request:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )
            
            # Get user role/scope from request
            user_scope = getattr(request.state, 'scope', None)
            
            # For now, we'll use scope as role. In production, you'd fetch from DB
            try:
                user_role = Role(user_scope)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid user role"
                )
            
            # Check permission
            if not RBACManager.has_permission(user_role, permission):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {permission.value}"
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    
    return decorator