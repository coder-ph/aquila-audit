"""
Unified report generator supporting multiple formats.
"""
from typing import Dict, List, Any, Optional
import os
from datetime import datetime
from pathlib import Path
import shutil

from shared.utils.logging import logger
from services.reporting_service.config import config
from services.reporting_service.generators.pdf_generator import pdf_generator
from services.reporting_service.generators.excel_generator import excel_generator
from services.reporting_service.generators.html_generator import html_generator
from services.reporting_service.generators.template_manager import template_manager


class ReportGenerator:
    """Main report generator that supports multiple formats."""
    
    def __init__(self):
        self.generators = {
            'pdf': pdf_generator,
            'excel': excel_generator,
            'html': html_generator
        }
    
    def generate_report(
    self,
    report_data: Dict[str, Any],
    output_format: str = 'pdf',
    output_dir: Optional[str] = None,
    tenant_id: Optional[str] = None,
    include_watermark: bool = True,
    include_signature: bool = True,
    include_charts: bool = True,
    include_interactive: bool = True,
    include_ai_explanations: bool = True
) -> Dict[str, Any]:
    """
    Generate report in specified format.
    
    Args:
        report_data: Report data
        output_format: pdf, excel, or html
        output_dir: Output directory (default: tenant's report directory)
        tenant_id: Tenant ID for file organization
        include_watermark: Whether to include watermark (PDF only)
        include_signature: Whether to include digital signature (PDF only)
        include_charts: Whether to include charts (Excel/HTML only)
        include_interactive: Whether to include interactive features (HTML only)
        include_ai_explanations: Whether to include AI explanations
    
    Returns:
        Generation metadata
    """
    if output_format not in self.generators:
        raise ValueError(f"Unsupported format: {output_format}. Supported: {list(self.generators.keys())}")
    
    # Enhance report data with AI if requested
    if include_ai_explanations:
        try:
            from services.reporting_service.integrations.llm_integration import llm_integration
            report_data = llm_integration.enhance_report_with_ai(report_data)
        except Exception as e:
            logger.error(f"Failed to enhance report with AI: {str(e)}")
            # Continue without AI enhancements
    
    # Determine output directory
    if output_dir is None:
        if tenant_id:
            output_dir = Path(config.reports_dir) / str(tenant_id)
        else:
            output_dir = Path(config.reports_dir) / 'default'
    else:
        output_dir = Path(output_dir)
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    report_id = report_data.get('report_id', f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{report_id}_{timestamp}.{output_format}"
    output_path = output_dir / filename
    
    # Select generator based on format
    generator = self.generators[output_format]
    
    # Generate report with format-specific options
    if output_format == 'pdf':
        metadata = generator.generate_report(
            report_data=report_data,
            output_path=str(output_path),
            include_watermark=include_watermark,
            include_signature=include_signature,
            include_ai_explanations=include_ai_explanations
        )
    elif output_format == 'excel':
        metadata = generator.generate_report(
            report_data=report_data,
            output_path=str(output_path),
            include_charts=include_charts,
            include_ai_explanations=include_ai_explanations
        )
    elif output_format == 'html':
        metadata = generator.generate_report(
            report_data=report_data,
            output_path=str(output_path),
            include_interactive=include_interactive,
            include_ai_explanations=include_ai_explanations
        )
    
    # Add additional metadata
    metadata.update({
        'report_id': report_id,
        'tenant_id': tenant_id,
        'format': output_format,
        'filename': filename,
        'relative_path': str(output_path.relative_to(Path.cwd())) if output_path.is_relative_to(Path.cwd()) else str(output_path),
        'ai_enhanced': include_ai_explanations
    })
    
    return metadata
    
    def generate_multiple_formats(
        self,
        report_data: Dict[str, Any],
        formats: List[str] = None,
        output_dir: Optional[str] = None,
        tenant_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Generate report in multiple formats.
        
        Args:
            report_data: Report data
            formats: List of formats to generate (default: all)
            output_dir: Output directory
            tenant_id: Tenant ID
            **kwargs: Additional format-specific options
        
        Returns:
            Dictionary with results for each format
        """
        if formats is None:
            formats = list(self.generators.keys())
        
        results = {}
        
        for format_name in formats:
            if format_name in self.generators:
                try:
                    # Format-specific options
                    format_kwargs = {}
                    if format_name == 'pdf':
                        format_kwargs['include_watermark'] = kwargs.get('include_watermark', True)
                        format_kwargs['include_signature'] = kwargs.get('include_signature', True)
                    elif format_name == 'excel':
                        format_kwargs['include_charts'] = kwargs.get('include_charts', True)
                    elif format_name == 'html':
                        format_kwargs['include_interactive'] = kwargs.get('include_interactive', True)
                    
                    # Generate report
                    result = self.generate_report(
                        report_data=report_data,
                        output_format=format_name,
                        output_dir=output_dir,
                        tenant_id=tenant_id,
                        **format_kwargs
                    )
                    
                    results[format_name] = result
                    
                except Exception as e:
                    logger.error(f"Error generating {format_name} report: {str(e)}")
                    results[format_name] = {
                        'success': False,
                        'error': str(e),
                        'format': format_name
                    }
        
        return results
    
    def list_available_reports(
        self,
        tenant_id: Optional[str] = None,
        format_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List available reports.
        
        Args:
            tenant_id: Filter by tenant ID
            format_filter: Filter by format (pdf, excel, html)
        
        Returns:
            List of report metadata
        """
        reports = []
        base_dir = Path(config.reports_dir)
        
        # Determine search directory
        if tenant_id:
            search_dir = base_dir / str(tenant_id)
        else:
            search_dir = base_dir
        
        if not search_dir.exists():
            return reports
        
        # Scan for report files
        for file_path in search_dir.rglob('*.*'):
            if file_path.is_file():
                file_format = file_path.suffix[1:].lower()  # Remove dot
                
                # Apply format filter
                if format_filter and file_format != format_filter.lower():
                    continue
                
                # Get file metadata
                stat = file_path.stat()
                
                reports.append({
                    'filename': file_path.name,
                    'path': str(file_path),
                    'relative_path': str(file_path.relative_to(base_dir)),
                    'format': file_format,
                    'size': stat.st_size,
                    'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    'tenant_id': tenant_id or file_path.parent.name
                })
        
        # Sort by modification time (newest first)
        reports.sort(key=lambda x: x['modified'], reverse=True)
        
        return reports
    
    def cleanup_old_reports(
        self,
        max_age_days: Optional[int] = None,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Clean up old reports based on retention policy.
        
        Args:
            max_age_days: Maximum age in days (default: from config)
            tenant_id: Tenant ID to cleanup
        
        Returns:
            Cleanup statistics
        """
        if max_age_days is None:
            max_age_days = config.report_retention_days
        
        cutoff_time = datetime.now().timestamp() - (max_age_days * 24 * 60 * 60)
        stats = {
            'total_deleted': 0,
            'total_failed': 0,
            'deleted_files': [],
            'failed_files': []
        }
        
        base_dir = Path(config.reports_dir)
        
        # Determine cleanup directory
        if tenant_id:
            cleanup_dir = base_dir / str(tenant_id)
        else:
            cleanup_dir = base_dir
        
        if not cleanup_dir.exists():
            return stats
        
        # Find old files
        for file_path in cleanup_dir.rglob('*.*'):
            if file_path.is_file():
                file_age = file_path.stat().st_mtime
                
                if file_age < cutoff_time:
                    try:
                        file_path.unlink()
                        stats['total_deleted'] += 1
                        stats['deleted_files'].append(str(file_path))
                        logger.info(f"Deleted old report: {file_path}")
                    except Exception as e:
                        stats['total_failed'] += 1
                        stats['failed_files'].append({
                            'path': str(file_path),
                            'error': str(e)
                        })
                        logger.error(f"Failed to delete old report {file_path}: {str(e)}")
        
        # Clean up empty directories
        for dir_path in cleanup_dir.rglob('*'):
            if dir_path.is_dir():
                try:
                    if not any(dir_path.iterdir()):
                        dir_path.rmdir()
                        logger.info(f"Removed empty directory: {dir_path}")
                except Exception as e:
                    logger.error(f"Failed to remove directory {dir_path}: {str(e)}")
        
        return stats


# Global report generator instance
report_generator = ReportGenerator()