"""
Report metadata management and database tracking.
"""
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import desc, and_

from shared.database.session import get_db
from shared.models.report_models import Report, ReportMetadata
from shared.utils.logging import logger
from services.reporting_service.config import config


class ReportMetadataManager:
    """Manages report metadata in database."""
    
    def __init__(self):
        pass
    
    def create_report_metadata(
        self,
        report_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        report_type: str,
        file_path: str,
        report_data: Dict[str, Any],
        file_size: int = 0
    ) -> Report:
        """
        Create report metadata in database.
        
        Args:
            report_id: Report UUID
            tenant_id: Tenant UUID
            user_id: User UUID
            report_type: Report format (pdf, excel, html)
            file_path: Path to report file
            report_data: Report data
            file_size: Report file size in bytes
        
        Returns:
            Report object
        """
        db: Session = next(get_db())
        
        try:
            # Create report record
            report = Report(
                id=report_id,
                tenant_id=tenant_id,
                user_id=user_id,
                report_type=report_type,
                status='completed',
                file_path=file_path,
                file_size=file_size,
                parameters=report_data
            )
            
            db.add(report)
            db.flush()  # Get the report ID
            
            # Extract and store key metadata
            metadata_fields = [
                'title', 'report_id', 'generated_by', 'generated_date',
                'total_findings', 'risk_score', 'confidential'
            ]
            
            for field in metadata_fields:
                if field in report_data:
                    metadata = ReportMetadata(
                        report_id=report.id,
                        key=field,
                        value=json.dumps(report_data[field]) if not isinstance(report_data[field], (str, int, float, bool)) else str(report_data[field])
                    )
                    db.add(metadata)
            
            # Store findings count if available
            if 'findings' in report_data:
                findings_count = len(report_data['findings'])
                metadata = ReportMetadata(
                    report_id=report.id,
                    key='findings_count',
                    value=str(findings_count)
                )
                db.add(metadata)
                
                # Store severity counts
                severity_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
                for finding in report_data['findings']:
                    severity = finding.get('severity', 'medium').lower()
                    if severity in severity_counts:
                        severity_counts[severity] += 1
                
                for severity, count in severity_counts.items():
                    if count > 0:
                        metadata = ReportMetadata(
                            report_id=report.id,
                            key=f'severity_{severity}_count',
                            value=str(count)
                        )
                        db.add(metadata)
            
            db.commit()
            
            logger.info(f"Report metadata created: {report_id}")
            
            return report
        
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create report metadata: {str(e)}")
            raise
    
    def get_report_metadata(self, report_id: UUID, tenant_id: Optional[UUID] = None) -> Optional[Dict[str, Any]]:
        """
        Get report metadata.
        
        Args:
            report_id: Report UUID
            tenant_id: Tenant UUID (optional, for security check)
        
        Returns:
            Report metadata dictionary
        """
        db: Session = next(get_db())
        
        try:
            query = db.query(Report).filter(Report.id == report_id)
            
            if tenant_id:
                query = query.filter(Report.tenant_id == tenant_id)
            
            report = query.first()
            
            if not report:
                return None
            
            # Get additional metadata
            metadata_records = db.query(ReportMetadata).filter(
                ReportMetadata.report_id == report_id
            ).all()
            
            metadata_dict = {record.key: record.value for record in metadata_records}
            
            result = {
                'id': str(report.id),
                'tenant_id': str(report.tenant_id),
                'user_id': str(report.user_id),
                'report_type': report.report_type,
                'status': report.status,
                'file_path': report.file_path,
                'file_size': report.file_size,
                'created_at': report.created_at.isoformat() if report.created_at else None,
                'generated_at': report.generated_at.isoformat() if report.generated_at else None,
                'parameters': report.parameters,
                'metadata': metadata_dict
            }
            
            return result
        
        except Exception as e:
            logger.error(f"Failed to get report metadata: {str(e)}")
            return None
    
    def list_reports(
        self,
        tenant_id: UUID,
        report_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = 'created_at',
        order_desc: bool = True
    ) -> Dict[str, Any]:
        """
        List reports for a tenant.
        
        Args:
            tenant_id: Tenant UUID
            report_type: Filter by report type
            limit: Maximum results
            offset: Pagination offset
            order_by: Field to order by
            order_desc: Whether to order descending
        
        Returns:
            List of reports with pagination info
        """
        db: Session = next(get_db())
        
        try:
            query = db.query(Report).filter(Report.tenant_id == tenant_id)
            
            if report_type:
                query = query.filter(Report.report_type == report_type)
            
            # Apply ordering
            order_column = getattr(Report, order_by, Report.created_at)
            if order_desc:
                query = query.order_by(desc(order_column))
            else:
                query = query.order_by(order_column)
            
            # Get total count
            total = query.count()
            
            # Apply pagination
            reports = query.offset(offset).limit(limit).all()
            
            # Format results
            formatted_reports = []
            for report in reports:
                formatted_reports.append({
                    'id': str(report.id),
                    'report_type': report.report_type,
                    'status': report.status,
                    'file_path': report.file_path,
                    'file_size': report.file_size,
                    'created_at': report.created_at.isoformat() if report.created_at else None,
                    'generated_at': report.generated_at.isoformat() if report.generated_at else None,
                    'title': report.parameters.get('title', 'Untitled Report') if report.parameters else 'Untitled Report'
                })
            
            return {
                'reports': formatted_reports,
                'pagination': {
                    'total': total,
                    'limit': limit,
                    'offset': offset,
                    'has_more': (offset + limit) < total
                }
            }
        
        except Exception as e:
            logger.error(f"Failed to list reports: {str(e)}")
            return {'reports': [], 'pagination': {'total': 0, 'limit': limit, 'offset': offset, 'has_more': False}}
    
    def update_report_status(
        self,
        report_id: UUID,
        status: str,
        additional_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update report status.
        
        Args:
            report_id: Report UUID
            status: New status
            additional_data: Additional data to update
        
        Returns:
            True if updated successfully
        """
        db: Session = next(get_db())
        
        try:
            report = db.query(Report).filter(Report.id == report_id).first()
            
            if not report:
                logger.error(f"Report not found: {report_id}")
                return False
            
            report.status = status
            
            if status == 'completed':
                report.generated_at = datetime.now()
            
            if additional_data:
                if 'file_path' in additional_data:
                    report.file_path = additional_data['file_path']
                if 'file_size' in additional_data:
                    report.file_size = additional_data['file_size']
                if 'parameters' in additional_data:
                    report.parameters = additional_data['parameters']
            
            db.commit()
            
            logger.info(f"Report status updated: {report_id} -> {status}")
            
            return True
        
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update report status: {str(e)}")
            return False
    
    def delete_report_metadata(self, report_id: UUID) -> bool:
        """
        Delete report metadata.
        
        Args:
            report_id: Report UUID
        
        Returns:
            True if deleted successfully
        """
        db: Session = next(get_db())
        
        try:
            # Delete metadata records first
            db.query(ReportMetadata).filter(ReportMetadata.report_id == report_id).delete()
            
            # Delete report record
            deleted_count = db.query(Report).filter(Report.id == report_id).delete()
            
            db.commit()
            
            if deleted_count > 0:
                logger.info(f"Report metadata deleted: {report_id}")
                return True
            else:
                logger.warning(f"Report not found for deletion: {report_id}")
                return False
        
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to delete report metadata: {str(e)}")
            return False
    
    def cleanup_old_metadata(
        self,
        max_age_days: int = 365,
        tenant_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Clean up old report metadata.
        
        Args:
            max_age_days: Maximum age in days
            tenant_id: Tenant ID (optional)
        
        Returns:
            Cleanup statistics
        """
        db: Session = next(get_db())
        
        try:
            cutoff_date = datetime.now() - timedelta(days=max_age_days)
            
            # Build query
            query = db.query(Report).filter(Report.created_at < cutoff_date)
            
            if tenant_id:
                query = query.filter(Report.tenant_id == tenant_id)
            
            # Get reports to delete
            old_reports = query.all()
            report_ids = [report.id for report in old_reports]
            
            if not report_ids:
                return {
                    'deleted': 0,
                    'reports': [],
                    'error': None
                }
            
            # Delete metadata records
            db.query(ReportMetadata).filter(
                ReportMetadata.report_id.in_(report_ids)
            ).delete(synchronize_session=False)
            
            # Delete report records
            deleted_count = query.delete(synchronize_session=False)
            
            db.commit()
            
            logger.info(f"Cleaned up {deleted_count} old report metadata records")
            
            return {
                'deleted': deleted_count,
                'reports': [str(report_id) for report_id in report_ids[:100]],  # Limit output
                'cutoff_date': cutoff_date.isoformat(),
                'max_age_days': max_age_days
            }
        
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to cleanup old metadata: {str(e)}")
            return {
                'deleted': 0,
                'reports': [],
                'error': str(e)
            }
    
    def get_storage_usage(self, tenant_id: UUID) -> Dict[str, Any]:
        """
        Get storage usage statistics for a tenant.
        
        Args:
            tenant_id: Tenant UUID
        
        Returns:
            Storage usage statistics
        """
        db: Session = next(get_db())
        
        try:
            # Get total reports count and size
            reports = db.query(Report).filter(Report.tenant_id == tenant_id).all()
            
            total_reports = len(reports)
            total_size = sum(report.file_size or 0 for report in reports)
            
            # Get counts by type
            type_counts = {}
            for report in reports:
                report_type = report.report_type
                type_counts[report_type] = type_counts.get(report_type, 0) + 1
            
            # Get average size
            avg_size = total_size / total_reports if total_reports > 0 else 0
            
            return {
                'tenant_id': str(tenant_id),
                'total_reports': total_reports,
                'total_size_bytes': total_size,
                'total_size_mb': total_size / (1024 * 1024),
                'average_size_bytes': avg_size,
                'reports_by_type': type_counts,
                'last_report_date': max((report.created_at for report in reports), default=None)
            }
        
        except Exception as e:
            logger.error(f"Failed to get storage usage: {str(e)}")
            return {
                'tenant_id': str(tenant_id),
                'error': str(e)
            }


# Global metadata manager instance
report_metadata_manager = ReportMetadataManager()