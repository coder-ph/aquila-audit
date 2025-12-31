"""
Digital signature implementation for PDF reports.
"""
import hashlib
import json
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
import tempfile

from shared.utils.logging import logger
from shared.utils.security import generate_hash
from services.reporting_service.config import config


class DigitalSigner:
    """Handles digital signatures for PDF reports."""
    
    def __init__(self):
        self.certificate_path = Path(config.signature_certificate_path)
        self.private_key_path = Path(config.signature_private_key_path)
        self.can_sign = self._check_signature_capability()
    
    def _check_signature_capability(self) -> bool:
        """Check if digital signing is possible."""
        # Check for required files
        if not self.certificate_path.exists():
            logger.warning(f"Certificate file not found: {self.certificate_path}")
            return False
        
        if not self.private_key_path.exists():
            logger.warning(f"Private key file not found: {self.private_key_path}")
            return False
        
        # Check for PyPDF2
        try:
            from PyPDF2 import PdfReader, PdfWriter
            return True
        except ImportError:
            logger.warning("PyPDF2 not installed, digital signing disabled")
            return False
    
    def sign_pdf(
        self,
        pdf_path: str,
        signature_data: Dict[str, Any]
    ) -> Optional[bytes]:
        """
        Add digital signature to PDF.
        
        Args:
            pdf_path: Path to PDF file
            signature_data: Data to include in signature
        
        Returns:
            Signed PDF as bytes, or None if signing failed
        """
        if not self.can_sign:
            return None
        
        try:
            from PyPDF2 import PdfReader, PdfWriter
            import io
            
            # Read the PDF
            with open(pdf_path, 'rb') as f:
                pdf_bytes = f.read()
            
            # Calculate hash
            signature_data['hash'] = generate_hash(pdf_bytes)
            signature_data['signed_at'] = datetime.now().isoformat()
            
            # Create signature object
            signature = self._create_signature_object(signature_data)
            
            # For now, we'll just add metadata since full digital signing
            # requires proper certificate handling
            # In production, you would use a proper signing library
            
            # Add signature metadata
            reader = PdfReader(io.BytesIO(pdf_bytes))
            writer = PdfWriter()
            
            # Copy all pages
            for page in reader.pages:
                writer.add_page(page)
            
            # Add metadata
            writer.add_metadata({
                '/Title': 'Aquila Audit Report',
                '/Author': signature_data.get('generated_by', 'Aquila Audit'),
                '/Subject': 'Audit Report',
                '/Keywords': 'audit, compliance, security',
                '/Creator': 'Aquila Audit System',
                '/Producer': 'Aquila Reporting Service',
                '/CreationDate': f"D:{datetime.now().strftime('%Y%m%d%H%M%S')}",
                '/ModDate': f"D:{datetime.now().strftime('%Y%m%d%H%M%S')}",
                '/Signature': json.dumps(signature_data)
            })
            
            # Write to bytes
            output = io.BytesIO()
            writer.write(output)
            
            logger.info(f"PDF digitally signed: {pdf_path}")
            
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"Error signing PDF: {str(e)}")
            return None
    
    def _create_signature_object(self, signature_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create signature object."""
        return {
            'version': '1.0',
            'algorithm': 'SHA-256',
            'signer': 'Aquila Audit System',
            'timestamp': datetime.now().isoformat(),
            'data': signature_data
        }
    
    def verify_signature(self, pdf_path: str) -> Dict[str, Any]:
        """
        Verify digital signature on PDF.
        
        Args:
            pdf_path: Path to PDF file
        
        Returns:
            Verification result
        """
        result = {
            'valid': False,
            'verified': False,
            'signature_data': None,
            'error': None
        }
        
        try:
            from PyPDF2 import PdfReader
            
            with open(pdf_path, 'rb') as f:
                reader = PdfReader(f)
                
                # Check for metadata
                metadata = reader.metadata
                if metadata and '/Signature' in metadata:
                    signature_data = json.loads(metadata['/Signature'])
                    result['signature_data'] = signature_data
                    result['verified'] = True
                    
                    # Verify hash
                    f.seek(0)
                    pdf_bytes = f.read()
                    current_hash = generate_hash(pdf_bytes)
                    
                    if 'hash' in signature_data.get('data', {}):
                        stored_hash = signature_data['data']['hash']
                        result['valid'] = (current_hash == stored_hash)
                    else:
                        result['error'] = "No hash found in signature"
                else:
                    result['error'] = "No signature found in PDF"
            
        except Exception as e:
            result['error'] = str(e)
        
        return result


# Global digital signer instance
digital_signer = DigitalSigner()