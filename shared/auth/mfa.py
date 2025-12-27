import pyotp
import qrcode
from io import BytesIO
from typing import Optional, Tuple
from datetime import datetime, timedelta
import base64

from shared.utils.logging import logger


class MFAManager:
    """Multi-Factor Authentication manager."""
    
    def __init__(self, issuer_name: str = "Aquila Audit"):
        self.issuer_name = issuer_name
    
    def generate_secret_key(self) -> str:
        """
        Generate a new secret key for MFA.
        
        Returns:
            Base32 encoded secret key
        """
        return pyotp.random_base32()
    
    def generate_totp_uri(
        self,
        secret_key: str,
        user_email: str,
        user_id: str
    ) -> str:
        """
        Generate TOTP URI for QR code generation.
        
        Args:
            secret_key: Base32 secret key
            user_email: User email
            user_id: User identifier
        
        Returns:
            TOTP URI
        """
        totp = pyotp.TOTP(secret_key)
        return totp.provisioning_uri(
            name=user_email,
            issuer_name=self.issuer_name
        )
    
    def generate_qr_code(self, totp_uri: str) -> BytesIO:
        """
        Generate QR code image from TOTP URI.
        
        Args:
            totp_uri: TOTP URI
        
        Returns:
            BytesIO containing QR code image
        """
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(totp_uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        img_bytes = BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)
        
        return img_bytes
    
    def verify_code(self, secret_key: str, code: str) -> bool:
        """
        Verify TOTP code.
        
        Args:
            secret_key: Base32 secret key
            code: TOTP code to verify
        
        Returns:
            True if code is valid
        """
        totp = pyotp.TOTP(secret_key)
        return totp.verify(code)
    
    def verify_code_with_window(
        self,
        secret_key: str,
        code: str,
        window: int = 1
    ) -> bool:
        """
        Verify TOTP code with time window.
        
        Args:
            secret_key: Base32 secret key
            code: TOTP code to verify
            window: Time window size
        
        Returns:
            True if code is valid within window
        """
        totp = pyotp.TOTP(secret_key)
        return totp.verify(code, valid_window=window)
    
    def generate_recovery_codes(self, count: int = 10) -> list[str]:
        """
        Generate recovery codes for MFA.
        
        Args:
            count: Number of recovery codes
        
        Returns:
            List of recovery codes
        """
        import secrets
        codes = []
        for _ in range(count):
            # Generate 10-character recovery code
            code = ''.join(
                secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789')
                for _ in range(10)
            )
            codes.append(code)
        return codes
    
    def verify_recovery_code(
        self,
        code: str,
        used_codes: list[str],
        stored_codes: list[str]
    ) -> Tuple[bool, list[str]]:
        """
        Verify recovery code and update used codes.
        
        Args:
            code: Recovery code to verify
            used_codes: List of already used recovery codes
            stored_codes: List of stored recovery codes
        
        Returns:
            Tuple of (is_valid, updated_used_codes)
        """
        if code in used_codes:
            return False, used_codes
        
        if code not in stored_codes:
            return False, used_codes
        
        # Code is valid, mark as used
        used_codes.append(code)
        return True, used_codes
    
    def get_remaining_valid_codes(
        self,
        used_codes: list[str],
        stored_codes: list[str]
    ) -> list[str]:
        """
        Get remaining valid recovery codes.
        
        Args:
            used_codes: Used recovery codes
            stored_codes: All stored recovery codes
        
        Returns:
            List of remaining valid codes
        """
        return [code for code in stored_codes if code not in used_codes]


# Global MFA manager instance
mfa_manager = MFAManager()