"""
Storage and bulk operations API routes.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from fastapi.responses import FileResponse
from typing import List, Optional, Dict, Any
from uuid import UUID
from pathlib import Path

from shared.auth.middleware import get_current_user, verify_tenant_access
from shared.models.user_models import User
from shared.utils.logging import logger
from services.reporting_service.config import config
from services.reporting_service.storage.report_metadata import report_metadata_manager
from services.reporting_service.storage.bulk_operations import bulk_report_operations
from services.reporting_service.security.signature.digital_signer import digital_signer

# Create router
router = APIRouter(
    prefix=f"{config.api_prefix}/storage",
    tags=["storage"],
    dependencies=[Depends(get_current_user)]
)


@router.get("/usage")
async def get_storage_usage(
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get storage usage statistics.
    
    Args:
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        Storage usage statistics
    """
    try:
        usage_stats = report_metadata_manager.get_storage_usage(UUID(tenant_id))
        
        if 'error' in usage_stats:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=usage_stats['error']
            )
        
        return usage_stats
    
    except Exception as e:
        logger.error(f"Error getting storage usage: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get storage usage: {str(e)}"
        )


@router.get("/analysis")
async def analyze_storage(
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Analyze storage and provide recommendations.
    
    Args:
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        Storage analysis with recommendations
    """
    try:
        analysis = bulk_report_operations.get_storage_analysis(UUID(tenant_id))
        
        if 'error' in analysis:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=analysis['error']
            )
        
        return analysis
    
    except Exception as e:
        logger.error(f"Error analyzing storage: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze storage: {str(e)}"
        )


@router.post("/export")
async def export_reports(
    report_ids: List[str],
    export_format: str = Query("zip", regex="^(zip|directory)$"),
    include_metadata: bool = Query(True),
    compress: bool = Query(True),
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Export multiple reports.
    
    Args:
        report_ids: List of report IDs to export
        export_format: Export format (zip, directory)
        include_metadata: Whether to include metadata
        compress: Whether to compress the export
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        Export result
    """
    try:
        # Convert string IDs to UUIDs
        report_uuids = [UUID(rid) for rid in report_ids]
        
        result = bulk_report_operations.export_reports(
            tenant_id=UUID(tenant_id),
            report_ids=report_uuids,
            output_format=export_format,
            include_metadata=include_metadata,
            compress=compress
        )
        
        if not result['success']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get('error', 'Export failed')
            )
        
        return result
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid report ID format: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error exporting reports: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export reports: {str(e)}"
        )


@router.delete("/bulk-delete")
async def delete_reports(
    report_ids: List[str],
    delete_files: bool = Query(True),
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Delete multiple reports.
    
    Args:
        report_ids: List of report IDs to delete
        delete_files: Whether to delete physical files
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        Delete result
    """
    try:
        # Convert string IDs to UUIDs
        report_uuids = [UUID(rid) for rid in report_ids]
        
        result = bulk_report_operations.delete_reports(
            tenant_id=UUID(tenant_id),
            report_ids=report_uuids,
            delete_files=delete_files
        )
        
        return result
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid report ID format: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error deleting reports: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete reports: {str(e)}"
        )


@router.post("/compress")
async def compress_reports(
    background_tasks: BackgroundTasks,
    report_ids: Optional[List[str]] = None,
    compression_level: int = Query(6, ge=1, le=9),
    delete_originals: bool = Query(False),
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Compress multiple reports.
    
    Args:
        report_ids: List of report IDs (None for all reports)
        compression_level: Compression level (1-9)
        delete_originals: Whether to delete original files
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        Compression result
    """
    try:
        report_uuids = None
        if report_ids:
            report_uuids = [UUID(rid) for rid in report_ids]
        
        # Run compression in background
        background_tasks.add_task(
            bulk_report_operations.compress_reports,
            tenant_id=UUID(tenant_id),
            report_ids=report_uuids,
            compression_level=compression_level,
            delete_originals=delete_originals
        )
        
        return {
            "message": "Compression task started in background",
            "tenant_id": tenant_id,
            "compression_level": compression_level,
            "delete_originals": delete_originals,
            "report_count": len(report_ids) if report_ids else "all"
        }
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid report ID format: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error scheduling compression: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to schedule compression: {str(e)}"
        )


@router.get("/download-export/{export_id}")
async def download_export(
    export_id: str,
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> FileResponse:
    """
    Download an export file.
    
    Args:
        export_id: Export ID
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        Export file
    """
    try:
        # Look for export file
        export_dir = Path(config.reports_dir) / 'exports' / tenant_id
        
        # Try zip file first
        export_path = export_dir / f"{export_id}.zip"
        if not export_path.exists():
            # Try directory
            export_path = export_dir / export_id
            if not export_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Export not found: {export_id}"
                )
        
        if export_path.is_dir():
            # Create zip of directory
            zip_path = export_path.with_suffix('.zip')
            import shutil
            shutil.make_archive(str(zip_path.with_suffix('')), 'zip', str(export_path))
            export_path = zip_path
        
        return FileResponse(
            path=export_path,
            filename=export_path.name,
            media_type="application/zip"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading export: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download export: {str(e)}"
        )


@router.post("/sign/{report_id}")
async def sign_report(
    report_id: str,
    background_tasks: BackgroundTasks,
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Digitally sign a report.
    
    Args:
        report_id: Report ID or filename
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        Signing result
    """
    try:
        # Get report metadata to find file path
        report_metadata = report_metadata_manager.get_report_metadata(
            UUID(report_id) if len(report_id) == 36 else None,
            UUID(tenant_id)
        )
        
        if not report_metadata:
            # Try to find by filename
            report_path = Path(config.reports_dir) / tenant_id / report_id
            if not report_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Report not found: {report_id}"
                )
        else:
            report_path = Path(report_metadata['file_path'])
            if not report_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Report file not found: {report_metadata['file_path']}"
                )
        
        # Sign in background
        background_tasks.add_task(
            digital_signer.sign_report,
            report_path=str(report_path),
            signature_data={
                'signed_by': current_user.email or current_user.username,
                'signed_by_id': str(current_user.id),
                'tenant_id': tenant_id,
                'report_id': report_id
            }
        )
        
        return {
            "message": "Digital signing started in background",
            "report_id": report_id,
            "report_path": str(report_path),
            "signed_by": current_user.email or current_user.username
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scheduling signing: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to schedule signing: {str(e)}"
        )


@router.get("/verify/{report_id}")
async def verify_report_signature(
    report_id: str,
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Verify report digital signature.
    
    Args:
        report_id: Report ID or filename
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        Verification result
    """
    try:
        # Get report metadata to find file path
        report_metadata = report_metadata_manager.get_report_metadata(
            UUID(report_id) if len(report_id) == 36 else None,
            UUID(tenant_id)
        )
        
        if not report_metadata:
            # Try to find by filename
            report_path = Path(config.reports_dir) / tenant_id / report_id
            if not report_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Report not found: {report_id}"
                )
        else:
            report_path = Path(report_metadata['file_path'])
            if not report_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Report file not found: {report_metadata['file_path']}"
                )
        
        # Verify signature
        verification_result = digital_signer.verify_signature(str(report_path))
        
        return verification_result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying signature: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify signature: {str(e)}"
        )


@router.post("/cleanup-metadata")
async def cleanup_report_metadata(
    background_tasks: BackgroundTasks,
    max_age_days: int = Query(365, ge=1, le=3650),
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Clean up old report metadata from database.
    
    Args:
        max_age_days: Maximum age in days
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        Cleanup result
    """
    try:
        # Run cleanup in background
        background_tasks.add_task(
            report_metadata_manager.cleanup_old_metadata,
            max_age_days=max_age_days,
            tenant_id=UUID(tenant_id)
        )
        
        return {
            "message": "Metadata cleanup started in background",
            "tenant_id": tenant_id,
            "max_age_days": max_age_days
        }
    
    except Exception as e:
        logger.error(f"Error scheduling metadata cleanup: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to schedule cleanup: {str(e)}"
        )