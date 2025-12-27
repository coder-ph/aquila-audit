from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from uuid import UUID

from shared.database.session import get_db_session, get_session
from shared.auth.jwt_handler import jwt_handler
from shared.auth.password import PasswordManager, generate_secure_password
from shared.auth.mfa import mfa_manager
from shared.utils.logging import logger

from services.api_gateway.dependencies.auth import get_current_user
from services.api_gateway.dependencies.tenant import get_tenant_context

# Create router
router = APIRouter()

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(
    email: str = Body(..., description="User email"),
    password: str = Body(..., description="User password"),
    full_name: str = Body(..., description="Full name"),
    company: Optional[str] = Body(None, description="Company name"),
    db: Session = Depends(get_db_session)
):
    """
    Register a new user.
    
    Note: In production, this would include email verification,
    captcha, etc.
    """
    # Check if user already exists
    # This is a placeholder - implement proper user model later
    from shared.models.user_models import User  # Will be created in next sprint
    
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )
    
    # Validate password strength
    is_valid, errors = PasswordManager.validate_password_strength(password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password validation failed: {', '.join(errors)}"
        )
    
    # Hash password
    hashed_password = PasswordManager.get_password_hash(password)
    
    # Create user
    # This is simplified - will be expanded in next sprint
    user = User(
        email=email,
        hashed_password=hashed_password,
        full_name=full_name,
        company=company,
        is_active=True
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    logger.info(f"User registered: {email}")
    
    return {
        "message": "User registered successfully",
        "user_id": str(user.id),
        "email": user.email
    }


@router.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db_session)
):
    """
    Login user and return tokens.
    """
    # Find user
    from shared.models.user_models import User  # Will be created in next sprint
    
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify password
    if not PasswordManager.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated"
        )
    
    # Get tenant (simplified - will be improved)
    tenant_id = None
    if user.tenants:
        tenant_id = user.tenants[0].id
    
    # Generate tokens
    tokens = jwt_handler.create_tokens_pair(
        user_id=user.id,
        tenant_id=tenant_id,
        scope="user"  # Default scope
    )
    
    logger.info(f"User logged in: {user.email}", user_id=str(user.id))
    
    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": tokens["token_type"],
        "user_id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "tenant_id": str(tenant_id) if tenant_id else None
    }


@router.post("/refresh")
async def refresh_token(
    refresh_token: str = Body(..., embed=True)
):
    """
    Refresh access token using refresh token.
    """
    new_access_token = jwt_handler.refresh_access_token(refresh_token)
    
    if not new_access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
    
    return {
        "access_token": new_access_token,
        "token_type": "bearer"
    }


@router.post("/logout")
async def logout(
    user_info: tuple = Depends(get_current_user)
):
    """
    Logout user.
    
    Note: In production, you would blacklist the token.
    For JWT, since they're stateless, we rely on short expiration.
    """
    user_id, tenant_id = user_info
    
    logger.info(f"User logged out", user_id=str(user_id), tenant_id=str(tenant_id))
    
    return {"message": "Successfully logged out"}


@router.post("/change-password")
async def change_password(
    current_password: str = Body(...),
    new_password: str = Body(...),
    user_info: tuple = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """
    Change user password.
    """
    user_id, tenant_id = user_info
    
    # Get user
    from shared.models.user_models import User
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Verify and update password
    success, result = PasswordManager.verify_and_update(
        current_password=current_password,
        new_password=new_password,
        hashed_current_password=user.hashed_password
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result
        )
    
    # Update password
    user.hashed_password = result
    db.commit()
    
    logger.info(f"Password changed", user_id=str(user_id))
    
    return {"message": "Password changed successfully"}


@router.post("/reset-password-request")
async def reset_password_request(
    email: str = Body(...),
    db: Session = Depends(get_db_session)
):
    """
    Request password reset.
    
    Note: In production, this would send an email with reset link.
    """
    # Find user
    from shared.models.user_models import User
    
    user = db.query(User).filter(User.email == email).first()
    if not user:
        # Don't reveal if user exists for security
        return {"message": "If the email exists, a reset link will be sent"}
    
    # Generate reset token (simplified)
    reset_token = jwt_handler.create_access_token(
        data={"sub": str(user.id), "type": "password_reset"},
        expires_delta=timedelta(hours=24)
    )
    
    # In production: Send email with reset link
    reset_link = f"https://yourapp.com/reset-password?token={reset_token}"
    
    logger.info(f"Password reset requested: {email}")
    
    return {
        "message": "If the email exists, a reset link will be sent",
        "reset_token": reset_token  # Remove in production
    }


@router.post("/reset-password")
async def reset_password(
    token: str = Body(...),
    new_password: str = Body(...)
):
    """
    Reset password using reset token.
    """
    # Verify token
    payload = jwt_handler.verify_token(token)
    if not payload or payload.get("type") != "password_reset":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    user_id = UUID(payload.get("sub"))
    
    # Get user
    from shared.models.user_models import User
    
    with get_session() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Validate new password
        is_valid, errors = PasswordManager.validate_password_strength(new_password)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Password validation failed: {', '.join(errors)}"
            )
        
        # Update password
        user.hashed_password = PasswordManager.get_password_hash(new_password)
        db.commit()
    
    logger.info(f"Password reset", user_id=str(user_id))
    
    return {"message": "Password reset successfully"}


@router.get("/me")
async def get_current_user_info(
    user_info: tuple = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """
    Get current user information.
    """
    user_id, tenant_id = user_info
    
    # Get user
    from shared.models.user_models import User
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Return user info (excluding sensitive data)
    return {
        "user_id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "company": user.company,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "tenant_id": str(tenant_id) if tenant_id else None
    }