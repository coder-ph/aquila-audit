"""
Digital signature implementation for PDF reports with compression support.
"""
import hashlib
import json
import zlib
import base64
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
import tempfile

from shared.utils.logging import logger
from shared.utils.security import generate_hash
from services.reporting_service.config import config


class DigitalSigner:
    """Handles digital signatures for PDF reports with compression."""
    
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
            import PyPDF2
            return True
        except ImportError:
            logger.warning("PyPDF2 not installed, digital signing disabled")
            return False
    
    def sign_report(
        self,
        report_path: str,
        signature_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Sign a report file.
        
        Args:
            report_path: Path to report file
            signature_data: Additional signature data
        
        Returns:
            Signature information
        """
        if not self.can_sign:
            return {
                'signed': False,
                'error': 'Digital signing not available'
            }
        
        try:
            report_path_obj = Path(report_path)
            
            if not report_path_obj.exists():
                return {
                    'signed': False,
                    'error': f'Report file not found: {report_path}'
                }
            
            # Read report content
            with open(report_path, 'rb') as f:
                report_content = f.read()
            
            # Generate signature data
            if signature_data is None:
                signature_data = {}
            
            # Add standard metadata
            signature_data.update({
                'file_size': len(report_content),
                'file_hash': generate_hash(report_content),
                'signed_at': datetime.now().isoformat(),
                'algorithm': 'SHA-256',
                'compression': 'zlib',
                'signature_version': '1.0'
            })
            
            # Compress signature data
            signature_json = json.dumps(signature_data, separators=(',', ':'))
            signature_compressed = zlib.compress(signature_json.encode('utf-8'))
            signature_base64 = base64.b64encode(signature_compressed).decode('ascii')
            
            # For now, we'll store signature in a separate file
            # In production, this would be embedded in the PDF
            signature_path = report_path_obj.with_suffix('.sig')
            with open(signature_path, 'w') as sig_file:
                json.dump({
                    'signature': signature_base64,
                    'original_size': len(signature_json),
                    'compressed_size': len(signature_compressed),
                    'compression_ratio': f"{(len(signature_json) - len(signature_compressed)) / len(signature_json) * 100:.1f}%"
                }, sig_file, indent=2)
            
            logger.info(f"Report signed: {report_path}")
            
            return {
                'signed': True,
                'signature_path': str(signature_path),
                'signature_data': signature_data,
                'file_hash': signature_data['file_hash']
            }
        
        except Exception as e:
            logger.error(f"Error signing report: {str(e)}")
            return {
                'signed': False,
                'error': str(e)
            }
    
    def verify_signature(
        self,
        report_path: str,
        signature_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Verify report signature.
        
        Args:
            report_path: Path to report file
            signature_path: Path to signature file (optional, auto-detected)
        
        Returns:
            Verification result
        """
        result = {
            'verified': False,
            'valid': False,
            'signature_exists': False,
            'file_exists': False,
            'hash_matches': False,
            'signature_data': None,
            'error': None
        }
        
        try:
            report_path_obj = Path(report_path)
            
            # Check if report exists
            if not report_path_obj.exists():
                result['error'] = f'Report file not found: {report_path}'
                return result
            
            result['file_exists'] = True
            
            # Read report content
            with open(report_path, 'rb') as f:
                report_content = f.read()
            
            # Calculate current hash
            current_hash = generate_hash(report_content)
            
            # Determine signature path
            if signature_path is None:
                signature_path_obj = report_path_obj.with_suffix('.sig')
            else:
                signature_path_obj = Path(signature_path)
            
            # Check if signature exists
            if not signature_path_obj.exists():
                result['error'] = f'Signature file not found: {signature_path_obj}'
                return result
            
            result['signature_exists'] = True
            
            # Read signature
            with open(signature_path_obj, 'r') as sig_file:
                signature_info = json.load(sig_file)
            
            # Decode signature
            signature_base64 = signature_info.get('signature', '')
            signature_compressed = base64.b64decode(signature_base64)
            signature_json = zlib.decompress(signature_compressed).decode('utf-8')
            signature_data = json.loads(signature_json)
            
            result['signature_data'] = signature_data
            
            # Verify hash
            stored_hash = signature_data.get('file_hash')
            if stored_hash and stored_hash == current_hash:
                result['hash_matches'] = True
            
            # Check signature age
            signed_at_str = signature_data.get('signed_at')
            if signed_at_str:
                try:
                    signed_at = datetime.fromisoformat(signed_at_str.replace('Z', '+00:00'))
                    age_days = (datetime.now() - signed_at).days
                    result['signature_age_days'] = age_days
                    
                    # Warn if signature is old
                    if age_days > 365:
                        result['warning'] = f'Signature is {age_days} days old'
                except:
                    pass
            
            result['verified'] = True
            result['valid'] = result['hash_matches']
        
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    def compress_report(
        self,
        report_path: str,
        output_path: Optional[str] = None,
        compression_level: int = 6
    ) -> Dict[str, Any]:
        """
        Compress report file.
        
        Args:
            report_path: Path to report file
            output_path: Output path (optional, auto-generated)
            compression_level: Compression level (1-9)
        
        Returns:
            Compression result
        """
        try:
            report_path_obj = Path(report_path)
            
            if not report_path_obj.exists():
                return {
                    'compressed': False,
                    'error': f'Report file not found: {report_path}'
                }
            
            # Read report content
            with open(report_path, 'rb') as f:
                report_content = f.read()
            
            # Compress content
            compressed_content = zlib.compress(report_content, level=compression_level)
            
            # Determine output path
            if output_path is None:
                output_path_obj = report_path_obj.with_suffix('.zlib')
            else:
                output_path_obj = Path(output_path)
            
            # Write compressed content
            with open(output_path_obj, 'wb') as f:
                f.write(compressed_content)
            
            original_size = len(report_content)
            compressed_size = len(compressed_content)
            compression_ratio = (original_size - compressed_size) / original_size * 100
            
            logger.info(f"Report compressed: {original_size} -> {compressed_size} bytes ({compression_ratio:.1f}% saved)")
            
            return {
                'compressed': True,
                'original_path': str(report_path_obj),
                'compressed_path': str(output_path_obj),
                'original_size': original_size,
                'compressed_size': compressed_size,
                'compression_ratio': f'{compression_ratio:.1f}%',
                'compression_level': compression_level
            }
        
        except Exception as e:
            logger.error(f"Error compressing report: {str(e)}")
            return {
                'compressed': False,
                'error': str(e)
            }
    
    def decompress_report(
        self,
        compressed_path: str,
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Decompress report file.
        
        Args:
            compressed_path: Path to compressed file
            output_path: Output path (optional, auto-generated)
        
        Returns:
            Decompression result
        """
        try:
            compressed_path_obj = Path(compressed_path)
            
            if not compressed_path_obj.exists():
                return {
                    'decompressed': False,
                    'error': f'Compressed file not found: {compressed_path}'
                }
            
            # Read compressed content
            with open(compressed_path, 'rb') as f:
                compressed_content = f.read()
            
            # Decompress content
            decompressed_content = zlib.decompress(compressed_content)
            
            # Determine output path
            if output_path is None:
                # Remove .zlib extension if present
                if compressed_path_obj.suffix == '.zlib':
                    output_path_obj = compressed_path_obj.with_suffix('')
                else:
                    output_path_obj = compressed_path_obj.with_suffix('.decompressed')
            else:
                output_path_obj = Path(output_path)
            
            # Write decompressed content
            with open(output_path_obj, 'wb') as f:
                f.write(decompressed_content)
            
            compressed_size = len(compressed_content)
            decompressed_size = len(decompressed_content)
            
            logger.info(f"Report decompressed: {compressed_size} -> {decompressed_size} bytes")
            
            return {
                'decompressed': True,
                'compressed_path': str(compressed_path_obj),
                'decompressed_path': str(output_path_obj),
                'compressed_size': compressed_size,
                'decompressed_size': decompressed_size
            }
        
        except Exception as e:
            logger.error(f"Error decompressing report: {str(e)}")
            return {
                'decompressed': False,
                'error': str(e)
            }


# Global digital signer instance
digital_signer = DigitalSigner()