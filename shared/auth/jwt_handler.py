from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from uuid import UUID

from shared.utils.config import settings
from shared.utils.logging import logger


class JWTTokenHandler:
    """Handler for JWT token operations."""
    
    def __init__(self):
        self.secret_key = settings.secret_key
        self.algorithm = settings.jwt_algorithm
        self.access_token_expire_minutes = settings.access_token_expire_minutes
    
    def create_access_token(
        self,
        data: Dict[str, Any],
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        Create a new access token.
        
        Args:
            data: Data to encode in token
            expires_delta: Optional expiration delta
        
        Returns:
            Encoded JWT token
        """
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                minutes=self.access_token_expire_minutes
            )
        
        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access"
        })
        
        encoded_jwt = jwt.encode(
            to_encode,
            self.secret_key,
            algorithm=self.algorithm
        )
        
        return encoded_jwt
    
    def create_refresh_token(
        self,
        user_id: UUID,
        tenant_id: Optional[UUID] = None
    ) -> str:
        """
        Create a refresh token.
        
        Args:
            user_id: User ID
            tenant_id: Tenant ID
        
        Returns:
            Encoded refresh token
        """
        to_encode = {
            "sub": str(user_id),
            "type": "refresh",
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(days=7)
        }
        
        if tenant_id:
            to_encode["tenant_id"] = str(tenant_id)
        
        encoded_jwt = jwt.encode(
            to_encode,
            self.secret_key,
            algorithm=self.algorithm
        )
        
        return encoded_jwt
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify and decode a token.
        
        Args:
            token: JWT token
        
        Returns:
            Decoded token payload or None
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
            return payload
        except JWTError as e:
            logger.error(f"JWT verification failed: {str(e)}")
            return None
    
    def refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """
        Create new access token from refresh token.
        
        Args:
            refresh_token: Valid refresh token
        
        Returns:
            New access token or None
        """
        payload = self.verify_token(refresh_token)
        
        if not payload or payload.get("type") != "refresh":
            return None
        
        # Create new access token with user info from refresh token
        access_token = self.create_access_token({
            "sub": payload.get("sub"),
            "tenant_id": payload.get("tenant_id"),
            "scope": payload.get("scope", "user")
        })
        
        return access_token
    
    def create_tokens_pair(
        self,
        user_id: UUID,
        tenant_id: Optional[UUID] = None,
        scope: str = "user"
    ) -> Dict[str, str]:
        """
        Create both access and refresh tokens.
        
        Args:
            user_id: User ID
            tenant_id: Tenant ID
            scope: Token scope
        
        Returns:
            Dictionary with access and refresh tokens
        """
        access_token = self.create_access_token({
            "sub": str(user_id),
            "tenant_id": str(tenant_id) if tenant_id else None,
            "scope": scope
        })
        
        refresh_token = self.create_refresh_token(user_id, tenant_id)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }


# Global JWT handler instance
jwt_handler = JWTTokenHandler()