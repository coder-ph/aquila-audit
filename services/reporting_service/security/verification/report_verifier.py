"""
Report verification and validation.
"""
import hashlib
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

from shared.utils.logging import logger
from shared.utils.security import generate_hash
from services.reporting_service.config import config


class ReportVerifier:
    """Verifies report integrity and authenticity."""
    
    def __init__(self):
        pass
    
    def verify_report_integrity(
        self,
        report_path: str,
        expected_hash: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Verify report file integrity.
        
        Args:
            report_path: Path to report file
            expected_hash: Expected file hash (optional)
        
        Returns:
            Verification result
        """
        result = {
            'valid': False,
            'verified': False,
            'file_exists': False,
            'file_size': 0,
            'calculated_hash': None,
            'matches_expected': False,
            'error': None
        }
        
        try:
            report_path_obj = Path(report_path)
            
            # Check if file exists
            if not report_path_obj.exists():
                result['error'] = f"File not found: {report_path}"
                return result
            
            result['file_exists'] = True
            result['file_size'] = report_path_obj.stat().st_size
            
            # Calculate file hash
            with open(report_path, 'rb') as f:
                file_content = f.read()
                result['calculated_hash'] = generate_hash(file_content)
            
            result['verified'] = True
            
            # Compare with expected hash if provided
            if expected_hash:
                result['matches_expected'] = (result['calculated_hash'] == expected_hash)
                result['valid'] = result['matches_expected']
            else:
                result['valid'] = True
            
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    def verify_report_structure(
        self,
        report_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Verify report data structure.
        
        Args:
            report_data: Report data to verify
        
        Returns:
            Verification result
        """
        result = {
            'valid': False,
            'errors': [],
            'warnings': [],
            'missing_fields': [],
            'field_counts': {}
        }
        
        # Required fields
        required_fields = ['report_id', 'title', 'generated_date']
        
        for field in required_fields:
            if field not in report_data:
                result['missing_fields'].append(field)
                result['errors'].append(f"Missing required field: {field}")
        
        # Check findings structure
        if 'findings' in report_data:
            findings = report_data['findings']
            result['field_counts']['findings'] = len(findings)
            
            # Check each finding
            for i, finding in enumerate(findings):
                if 'id' not in finding:
                    result['warnings'].append(f"Finding {i} missing id")
                if 'title' not in finding:
                    result['warnings'].append(f"Finding {i} missing title")
                if 'severity' not in finding:
                    result['warnings'].append(f"Finding {i} missing severity")
        
        # Check metrics structure
        if 'metrics' in report_data:
            metrics = report_data['metrics']
            expected_metrics = ['total_findings', 'critical', 'high', 'medium', 'low']
            
            for metric in expected_metrics:
                if metric not in metrics:
                    result['warnings'].append(f"Missing metric: {metric}")
        
        # Determine validity
        result['valid'] = len(result['errors']) == 0
        
        return result
    
    def generate_verification_report(
        self,
        report_path: str,
        report_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate comprehensive verification report.
        
        Args:
            report_path: Path to report file
            report_data: Report data
        
        Returns:
            Comprehensive verification report
        """
        integrity_result = self.verify_report_integrity(report_path)
        structure_result = self.verify_report_structure(report_data)
        
        # Digital signature verification
        signature_result = {'valid': False, 'verified': False, 'error': 'Not implemented'}
        
        if config.enable_digital_signatures:
            from services.reporting_service.security.signature import digital_signer
            signature_result = digital_signer.verify_signature(report_path)
        
        # Overall verification
        overall_valid = (
            integrity_result['valid'] and
            structure_result['valid'] and
            signature_result['valid']
        )
        
        return {
            'overall_valid': overall_valid,
            'timestamp': datetime.now().isoformat(),
            'integrity_check': integrity_result,
            'structure_check': structure_result,
            'signature_check': signature_result,
            'recommendations': self._generate_recommendations(
                integrity_result,
                structure_result,
                signature_result
            )
        }
    
    def _generate_recommendations(
        self,
        integrity_result: Dict[str, Any],
        structure_result: Dict[str, Any],
        signature_result: Dict[str, Any]
    ) -> List[str]:
        """Generate recommendations based on verification results."""
        recommendations = []
        
        # Integrity recommendations
        if not integrity_result['valid']:
            if integrity_result['error']:
                recommendations.append(f"Fix integrity issue: {integrity_result['error']}")
        
        # Structure recommendations
        if structure_result['errors']:
            recommendations.extend([
                f"Fix structure error: {error}"
                for error in structure_result['errors']
            ])
        
        if structure_result['warnings']:
            recommendations.extend([
                f"Address warning: {warning}"
                for warning in structure_result['warnings']
            ])
        
        # Signature recommendations
        if not signature_result['verified']:
            recommendations.append("Consider adding digital signature for authenticity")
        
        return recommendations


# Global verifier instance
report_verifier = ReportVerifier()