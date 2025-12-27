from passlib.context import CryptContext
from typing import Union
import secrets
import string

from shared.utils.logging import logger

# Password hashing context
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.
    
    Args:
        plain_password: Plain text password
        hashed_password: Hashed password
    
    Returns:
        True if password matches, False otherwise
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.error("Password verification failed", error=str(e))
        return False


def get_password_hash(password: str) -> str:
    """
    Hash a password.
    
    Args:
        password: Plain text password
    
    Returns:
        Hashed password
    """
    return pwd_context.hash(password)


def generate_secure_password(length: int = 16) -> str:
    """
    Generate a secure random password.
    
    Args:
        length: Length of password
    
    Returns:
        Secure password
    """
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(secrets.choice(alphabet) for _ in range(length))
    return password


def validate_password_strength(password: str) -> tuple[bool, list[str]]:
    """
    Validate password strength.
    
    Args:
        password: Password to validate
    
    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []
    
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long")
    
    if not any(c.isupper() for c in password):
        errors.append("Password must contain at least one uppercase letter")
    
    if not any(c.islower() for c in password):
        errors.append("Password must contain at least one lowercase letter")
    
    if not any(c.isdigit() for c in password):
        errors.append("Password must contain at least one digit")
    
    if not any(c in "!@#$%^&*" for c in password):
        errors.append("Password must contain at least one special character (!@#$%^&*)")
    
    return len(errors) == 0, errors


class PasswordManager:
    """Manager for password operations."""
    
    @staticmethod
    def create_password_hash(password: str) -> str:
        """Create password hash with validation."""
        is_valid, errors = validate_password_strength(password)
        if not is_valid:
            raise ValueError(f"Password validation failed: {', '.join(errors)}")
        return get_password_hash(password)
    
    @staticmethod
    def verify_and_update(
        current_password: str,
        new_password: str,
        hashed_current_password: str
    ) -> tuple[bool, Union[str, None]]:
        """
        Verify current password and hash new password.
        
        Args:
            current_password: Current plain text password
            new_password: New plain text password
            hashed_current_password: Hashed current password
        
        Returns:
            Tuple of (success, new_hashed_password_or_error)
        """
        # Verify current password
        if not verify_password(current_password, hashed_current_password):
            return False, "Current password is incorrect"
        
        # Validate new password strength
        is_valid, errors = validate_password_strength(new_password)
        if not is_valid:
            return False, f"New password validation failed: {', '.join(errors)}"
        
        # Hash new password
        new_hashed_password = get_password_hash(new_password)
        return True, new_hashed_password