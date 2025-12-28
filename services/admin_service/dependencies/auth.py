from fastapi import Header, HTTPException, status

from services.admin_service.config import config
from shared.utils.logging import logger


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