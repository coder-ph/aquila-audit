"""
Bulk report operations for storage management.
"""
import json
import shutil
import zipfile
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from shared.database.session import get_db
from shared.models.report_models import Report
from shared.utils.logging import logger
from services.reporting_service.config import config
from services.reporting_service.storage.report_metadata import report_metadata_manager


class BulkReportOperations:
    """Handles bulk operations on reports."""
    
    def __init__(self):
        self.reports_dir = Path(config.reports_dir)
    
    def export_reports(
        self,
        tenant_id: UUID,
        report_ids: List[UUID],
        output_format: str = 'zip',
        include_metadata: bool = True,
        compress: bool = True
    ) -> Dict[str, Any]:
        """
        Export multiple reports.
        
        Args:
            tenant_id: Tenant UUID
            report_ids: List of report IDs to export
            output_format: Export format (zip, directory)
            include_metadata: Whether to include metadata
            compress: Whether to compress the export
        
        Returns:
            Export result
        """
        start_time = datetime.now()
        
        try:
            db: Session = next(get_db())
            
            # Get reports from database
            reports = db.query(Report).filter(
                Report.tenant_id == tenant_id,
                Report.id.in_(report_ids)
            ).all()
            
            if not reports:
                return {
                    'success': False,
                    'error': 'No reports found for the specified IDs',
                    'exported': 0
                }
            
            # Create export directory
            export_dir = self.reports_dir / 'exports' / str(tenant_id)
            export_dir.mkdir(parents=True, exist_ok=True)
            
            export_id = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            export_base = export_dir / export_id
            
            if output_format == 'directory':
                export_path = export_base
                export_path.mkdir(parents=True, exist_ok=True)
            else:  # zip format
                export_path = export_base.with_suffix('.zip')
            
            exported_files = []
            skipped_files = []
            
            for report in reports:
                # Check if report file exists
                report_path = Path(report.file_path) if report.file_path else None
                
                if not report_path or not report_path.exists():
                    skipped_files.append({
                        'report_id': str(report.id),
                        'reason': 'File not found',
                        'file_path': report.file_path
                    })
                    continue
                
                # Prepare destination path
                if output_format == 'directory':
                    dest_path = export_path / report_path.name
                    shutil.copy2(report_path, dest_path)
                else:
                    # Will add to zip later
                    dest_path = report_path
                
                # Prepare metadata
                if include_metadata:
                    metadata_file = export_path / f"{report_path.stem}_metadata.json"
                    metadata = report_metadata_manager.get_report_metadata(report.id, tenant_id)
                    if metadata:
                        with open(metadata_file, 'w') as f:
                            json.dump(metadata, f, indent=2, default=str)
                
                exported_files.append({
                    'report_id': str(report.id),
                    'original_path': str(report_path),
                    'exported_path': str(dest_path),
                    'report_type': report.report_type,
                    'file_size': report_path.stat().st_size if report_path.exists() else 0
                })
            
            # Create zip file if requested
            if output_format == 'zip' and exported_files:
                with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED) as zipf:
                    for export_info in exported_files:
                        report_path = Path(export_info['original_path'])
                        if report_path.exists():
                            zipf.write(report_path, report_path.name)
                    
                    # Add metadata files if they exist
                    if include_metadata:
                        metadata_files = export_path.parent.glob("*_metadata.json")
                        for metadata_file in metadata_files:
                            zipf.write(metadata_file, metadata_file.name)
            
            # Calculate statistics
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            total_size = sum(f['file_size'] for f in exported_files)
            
            result = {
                'success': True,
                'export_id': export_id,
                'export_path': str(export_path),
                'export_format': output_format,
                'compressed': compress,
                'exported_files': len(exported_files),
                'skipped_files': len(skipped_files),
                'total_size_bytes': total_size,
                'export_duration': duration,
                'include_metadata': include_metadata,
                'details': {
                    'exported': exported_files,
                    'skipped': skipped_files
                }
            }
            
            logger.info(f"Exported {len(exported_files)} reports for tenant {tenant_id}")
            
            return result
        
        except Exception as e:
            logger.error(f"Failed to export reports: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'exported': 0
            }
    
    def delete_reports(
        self,
        tenant_id: UUID,
        report_ids: List[UUID],
        delete_files: bool = True
    ) -> Dict[str, Any]:
        """
        Delete multiple reports.
        
        Args:
            tenant_id: Tenant UUID
            report_ids: List of report IDs to delete
            delete_files: Whether to delete physical files
        
        Returns:
            Delete result
        """
        try:
            db: Session = next(get_db())
            
            # Get reports from database
            reports = db.query(Report).filter(
                Report.tenant_id == tenant_id,
                Report.id.in_(report_ids)
            ).all()
            
            if not reports:
                return {
                    'success': False,
                    'error': 'No reports found for the specified IDs',
                    'deleted': 0
                }
            
            deleted_reports = []
            failed_deletions = []
            
            for report in reports:
                try:
                    # Delete file if requested
                    if delete_files and report.file_path:
                        report_path = Path(report.file_path)
                        if report_path.exists():
                            report_path.unlink()
                    
                    # Delete from database
                    db.delete(report)
                    
                    deleted_reports.append({
                        'report_id': str(report.id),
                        'file_path': report.file_path,
                        'file_deleted': delete_files and report.file_path and Path(report.file_path).exists() is False
                    })
                
                except Exception as e:
                    failed_deletions.append({
                        'report_id': str(report.id),
                        'error': str(e)
                    })
            
            db.commit()
            
            result = {
                'success': True if not failed_deletions else False,
                'deleted': len(deleted_reports),
                'failed': len(failed_deletions),
                'total_attempted': len(report_ids),
                'details': {
                    'deleted': deleted_reports,
                    'failed': failed_deletions
                }
            }
            
            if deleted_reports:
                logger.info(f"Deleted {len(deleted_reports)} reports for tenant {tenant_id}")
            
            if failed_deletions:
                logger.warning(f"Failed to delete {len(failed_deletions)} reports")
            
            return result
        
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to delete reports: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'deleted': 0
            }
    
    def compress_reports(
        self,
        tenant_id: UUID,
        report_ids: Optional[List[UUID]] = None,
        compression_level: int = 6,
        delete_originals: bool = False
    ) -> Dict[str, Any]:
        """
        Compress multiple reports.
        
        Args:
            tenant_id: Tenant UUID
            report_ids: List of report IDs (None for all reports)
            compression_level: Compression level (1-9)
            delete_originals: Whether to delete original files after compression
        
        Returns:
            Compression result
        """
        start_time = datetime.now()
        
        try:
            db: Session = next(get_db())
            
            # Build query
            query = db.query(Report).filter(Report.tenant_id == tenant_id)
            
            if report_ids:
                query = query.filter(Report.id.in_(report_ids))
            
            reports = query.all()
            
            if not reports:
                return {
                    'success': False,
                    'error': 'No reports found',
                    'compressed': 0
                }
            
            compressed_reports = []
            failed_compressions = []
            total_original_size = 0
            total_compressed_size = 0
            
            from services.reporting_service.security.signature.digital_signer import digital_signer
            
            for report in reports:
                try:
                    # Check if file exists
                    if not report.file_path:
                        failed_compressions.append({
                            'report_id': str(report.id),
                            'error': 'No file path'
                        })
                        continue
                    
                    report_path = Path(report.file_path)
                    if not report_path.exists():
                        failed_compressions.append({
                            'report_id': str(report.id),
                            'error': 'File not found'
                        })
                        continue
                    
                    # Compress the file
                    compress_result = digital_signer.compress_report(
                        report_path=str(report_path),
                        compression_level=compression_level
                    )
                    
                    if compress_result['compressed']:
                        compressed_path = compress_result['compressed_path']
                        
                        # Update database if compression successful
                        if delete_originals:
                            # Delete original file
                            report_path.unlink()
                            
                            # Update report record with compressed path
                            report.file_path = compressed_path
                            report.file_size = compress_result['compressed_size']
                        
                        total_original_size += compress_result['original_size']
                        total_compressed_size += compress_result['compressed_size']
                        
                        compressed_reports.append({
                            'report_id': str(report.id),
                            'original_path': str(report_path),
                            'compressed_path': compressed_path,
                            'original_size': compress_result['original_size'],
                            'compressed_size': compress_result['compressed_size'],
                            'compression_ratio': compress_result['compression_ratio'],
                            'original_deleted': delete_originals
                        })
                    else:
                        failed_compressions.append({
                            'report_id': str(report.id),
                            'error': compress_result.get('error', 'Compression failed')
                        })
                
                except Exception as e:
                    failed_compressions.append({
                        'report_id': str(report.id),
                        'error': str(e)
                    })
            
            db.commit()
            
            # Calculate statistics
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            if total_original_size > 0:
                overall_ratio = (total_original_size - total_compressed_size) / total_original_size * 100
            else:
                overall_ratio = 0
            
            result = {
                'success': True if not failed_compressions else False,
                'compressed': len(compressed_reports),
                'failed': len(failed_compressions),
                'total_original_size': total_original_size,
                'total_compressed_size': total_compressed_size,
                'overall_compression_ratio': f'{overall_ratio:.1f}%',
                'space_saved': total_original_size - total_compressed_size,
                'compression_duration': duration,
                'compression_level': compression_level,
                'delete_originals': delete_originals,
                'details': {
                    'compressed': compressed_reports,
                    'failed': failed_compressions
                }
            }
            
            if compressed_reports:
                logger.info(f"Compressed {len(compressed_reports)} reports, saved {overall_ratio:.1f}% space")
            
            return result
        
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to compress reports: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'compressed': 0
            }
    
    def get_storage_analysis(self, tenant_id: UUID) -> Dict[str, Any]:
        """
        Analyze storage usage and provide recommendations.
        
        Args:
            tenant_id: Tenant UUID
        
        Returns:
            Storage analysis
        """
        try:
            # Get storage usage
            usage_stats = report_metadata_manager.get_storage_usage(tenant_id)
            
            if 'error' in usage_stats:
                return usage_stats
            
            # Analyze report types
            db: Session = next(get_db())
            reports = db.query(Report).filter(Report.tenant_id == tenant_id).all()
            
            # Analyze by age
            now = datetime.now()
            age_groups = {
                'last_week': 0,
                'last_month': 0,
                'last_quarter': 0,
                'older': 0
            }
            
            for report in reports:
                if report.created_at:
                    age_days = (now - report.created_at).days
                    
                    if age_days <= 7:
                        age_groups['last_week'] += 1
                    elif age_days <= 30:
                        age_groups['last_month'] += 1
                    elif age_days <= 90:
                        age_groups['last_quarter'] += 1
                    else:
                        age_groups['older'] += 1
            
            # Calculate compression potential
            # Assume different compression rates for different formats
            compression_rates = {
                'pdf': 0.20,  # 20% compression
                'excel': 0.40,  # 40% compression
                'html': 0.60,  # 60% compression
            }
            
            potential_savings = 0
            for report_type, count in usage_stats.get('reports_by_type', {}).items():
                avg_size = usage_stats.get('average_size_bytes', 0)
                rate = compression_rates.get(report_type, 0.30)  # Default 30%
                potential_savings += count * avg_size * rate
            
            # Generate recommendations
            recommendations = []
            
            if age_groups['older'] > 10:
                recommendations.append({
                    'type': 'cleanup',
                    'priority': 'medium',
                    'message': f"You have {age_groups['older']} reports older than 90 days. Consider archiving or deleting old reports.",
                    'action': 'cleanup_old_reports',
                    'estimated_savings': '10-30%'
                })
            
            if potential_savings > 100 * 1024 * 1024:  # More than 100MB
                recommendations.append({
                    'type': 'compression',
                    'priority': 'low',
                    'message': f'You could save approximately {potential_savings / (1024*1024):.1f} MB by compressing reports.',
                    'action': 'compress_reports',
                    'estimated_savings': f'{potential_savings / (1024*1024):.1f} MB'
                })
            
            if usage_stats['total_reports'] > 1000:
                recommendations.append({
                    'type': 'archive',
                    'priority': 'medium',
                    'message': f'You have {usage_stats["total_reports"]} reports. Consider implementing an archival strategy.',
                    'action': 'setup_archival',
                    'estimated_savings': 'N/A'
                })
            
            return {
                'analysis_date': now.isoformat(),
                'tenant_id': str(tenant_id),
                'usage_statistics': usage_stats,
                'age_distribution': age_groups,
                'potential_savings_bytes': potential_savings,
                'potential_savings_mb': potential_savings / (1024 * 1024),
                'recommendations': recommendations
            }
        
        except Exception as e:
            logger.error(f"Failed to analyze storage: {str(e)}")
            return {
                'error': str(e),
                'tenant_id': str(tenant_id)
            }


# Global bulk operations instance
bulk_report_operations = BulkReportOperations()