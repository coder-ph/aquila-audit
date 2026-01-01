"""
Report generation API routes.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path

from shared.auth.middleware import get_current_user, verify_tenant_access
from shared.models.user_models import User, Tenant
from shared.utils.logging import logger
from services.reporting_service.config import config
from services.reporting_service.generators.report_generator import report_generator
from services.reporting_service.templates.template_manager import template_manager
from services.reporting_service.security.verification import report_verifier

# Create router
router = APIRouter(
    prefix=config.api_prefix,
    tags=["reports"],
    dependencies=[Depends(get_current_user)]
)


@router.post("/generate", status_code=status.HTTP_201_CREATED)
async def generate_report(
    report_data: Dict[str, Any],
    background_tasks: BackgroundTasks,
    format: str = Query("pdf", regex="^(pdf|excel|html)$"),
    async_mode: bool = Query(True, description="Generate report asynchronously"),
    include_explanations: bool = Query(True, description="Include AI explanations"),
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Generate a new report.
    
    Args:
        report_data: Report data including findings, metrics, etc.
        format: Output format (pdf, excel, html)
        async_mode: Whether to generate asynchronously
        include_explanations: Whether to include AI explanations
        tenant_id: Tenant ID for isolation
        current_user: Current authenticated user
    
    Returns:
        Report generation metadata
    """
    try:
        import uuid
        from datetime import datetime
        
        # Generate report ID
        report_id = str(uuid.uuid4())
        
        # Add user and tenant info to report data
        if 'generated_by' not in report_data:
            report_data['generated_by'] = current_user.email or current_user.username
        
        if 'tenant' not in report_data:
            report_data['tenant'] = {
                'id': tenant_id,
                'name': f"Tenant {tenant_id}"
            }
        
        if 'generated_date' not in report_data:
            report_data['generated_date'] = datetime.now().isoformat()
        
        # Extract findings IDs if provided
        findings_ids = report_data.get('findings_ids', [])
        
        if async_mode:
            # Event-driven async generation
            from services.reporting_service.events.report_publisher import report_publisher
            
            # Publish report generation request
            success = report_publisher.publish_report_requested(
                tenant_id=tenant_id,
                report_id=report_id,
                report_type=format,
                findings_ids=findings_ids,
                user_id=str(current_user.id),
                include_explanations=include_explanations
            )
            
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to queue report generation"
                )
            
            # Create initial report record in database
            from shared.database.session import get_db
            from shared.models.report_models import Report
            import uuid as uuid_lib
            
            db = next(get_db())
            report = Report(
                id=uuid_lib.UUID(report_id),
                tenant_id=uuid_lib.UUID(tenant_id),
                user_id=current_user.id,
                report_type=format,
                status='queued',
                parameters=report_data
            )
            db.add(report)
            db.commit()
            
            return {
                'message': 'Report generation queued',
                'report_id': report_id,
                'status': 'queued',
                'async': True,
                'queue_position': 'report_generation_request',
                'estimated_completion': 'Check status via report status endpoint'
            }
        
        else:
            # Synchronous generation (for small reports)
            result = report_generator.generate_report(
                report_data=report_data,
                output_format=format,
                tenant_id=tenant_id
            )
            
            # Schedule cleanup if enabled
            if config.auto_cleanup_enabled:
                background_tasks.add_task(
                    report_generator.cleanup_old_reports,
                    tenant_id=tenant_id
                )
            
            return {
                'message': 'Report generated synchronously',
                'report_id': report_id,
                'status': 'completed',
                'async': False,
                'result': result
            }
        
    except Exception as e:
        logger.error(f"Error generating report: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate report: {str(e)}"
        )


# Add new endpoint for checking report status
@router.get("/status/{report_id}")
async def get_report_status(
    report_id: str,
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get report generation status.
    
    Args:
        report_id: Report ID
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        Report status information
    """
    try:
        from shared.database.session import get_db
        from shared.models.report_models import Report
        import uuid
        
        db = next(get_db())
        
        report = db.query(Report).filter(
            Report.id == uuid.UUID(report_id),
            Report.tenant_id == uuid.UUID(tenant_id)
        ).first()
        
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report {report_id} not found"
            )
        
        # Check if task is still running
        from services.worker_service.celery_app import celery_app
        from celery.result import AsyncResult
        
        task_id = f"report_{report_id}"
        task_result = AsyncResult(task_id, app=celery_app)
        
        status_info = {
            'report_id': report_id,
            'status': report.status,
            'report_type': report.report_type,
            'created_at': report.created_at.isoformat() if report.created_at else None,
            'generated_at': report.generated_at.isoformat() if report.generated_at else None,
            'celery_task_status': task_result.status if task_result else 'unknown',
            'task_id': task_id
        }
        
        # Add result if available
        if report.result_data:
            status_info['result'] = report.result_data
        
        # Add error if failed
        if report.status == 'failed' and report.result_data and 'error' in report.result_data:
            status_info['error'] = report.result_data['error']
        
        return status_info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting report status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get report status: {str(e)}"
        )


@router.post("/generate-multiple")
async def generate_multiple_formats(
    report_data: Dict[str, Any],
    background_tasks: BackgroundTasks,
    formats: List[str] = Query(["pdf", "excel", "html"]),
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Generate report in multiple formats.
    
    Args:
        report_data: Report data
        formats: List of formats to generate
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        Results for each format
    """
    try:
        # Add user and tenant info
        if 'generated_by' not in report_data:
            report_data['generated_by'] = current_user.email or current_user.username
        
        if 'tenant' not in report_data:
            report_data['tenant'] = {
                'id': tenant_id,
                'name': f"Tenant {tenant_id}"
            }
        
        if 'generated_date' not in report_data:
            report_data['generated_date'] = datetime.now().isoformat()
        
        # Generate reports in multiple formats
        results = report_generator.generate_multiple_formats(
            report_data=report_data,
            formats=formats,
            tenant_id=tenant_id
        )
        
        # Schedule cleanup
        if config.auto_cleanup_enabled:
            background_tasks.add_task(
                report_generator.cleanup_old_reports,
                tenant_id=tenant_id
            )
        
        return {"formats": results}
        
    except Exception as e:
        logger.error(f"Error generating multiple format reports: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate reports: {str(e)}"
        )


@router.get("/list")
async def list_reports(
    format: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    List available reports for the tenant.
    
    Args:
        format: Filter by format
        limit: Maximum number of results
        offset: Pagination offset
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        List of reports with pagination info
    """
    try:
        reports = report_generator.list_available_reports(
            tenant_id=tenant_id,
            format_filter=format
        )
        
        # Apply pagination
        total = len(reports)
        paginated_reports = reports[offset:offset + limit]
        
        return {
            "reports": paginated_reports,
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total
            }
        }
        
    except Exception as e:
        logger.error(f"Error listing reports: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list reports: {str(e)}"
        )


@router.get("/download/{filename}")
async def download_report(
    filename: str,
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> FileResponse:
    """
    Download a specific report.
    
    Args:
        filename: Report filename
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        File response with the report
    """
    try:
        # Construct file path with tenant isolation
        file_path = Path(config.reports_dir) / str(tenant_id) / filename
        
        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report not found: {filename}"
            )
        
        # Verify the file belongs to the tenant
        if str(file_path.parent.name) != str(tenant_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this report"
            )
        
        # Determine media type based on file extension
        media_type = "application/octet-stream"
        if filename.endswith('.pdf'):
            media_type = "application/pdf"
        elif filename.endswith(('.xlsx', '.xls')):
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif filename.endswith('.html'):
            media_type = "text/html"
        
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type=media_type
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading report: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download report: {str(e)}"
        )


@router.post("/verify/{filename}")
async def verify_report(
    filename: str,
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Verify report integrity and authenticity.
    
    Args:
        filename: Report filename
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        Verification results
    """
    try:
        # Construct file path
        file_path = Path(config.reports_dir) / str(tenant_id) / filename
        
        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report not found: {filename}"
            )
        
        # For now, we'll use minimal report data
        # In production, you might want to load the actual report data
        report_data = {
            'filename': filename,
            'tenant_id': tenant_id
        }
        
        # Run verification
        verification_result = report_verifier.generate_verification_report(
            report_path=str(file_path),
            report_data=report_data
        )
        
        return verification_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying report: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify report: {str(e)}"
        )


@router.delete("/cleanup")
async def cleanup_reports(
    background_tasks: BackgroundTasks,
    max_age_days: Optional[int] = None,
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Clean up old reports.
    
    Args:
        max_age_days: Maximum age in days
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        Cleanup statistics
    """
    try:
        # Run cleanup in background
        background_tasks.add_task(
            report_generator.cleanup_old_reports,
            max_age_days=max_age_days,
            tenant_id=tenant_id
        )
        
        return {
            "message": "Cleanup task started",
            "tenant_id": tenant_id,
            "max_age_days": max_age_days or config.report_retention_days
        }
        
    except Exception as e:
        logger.error(f"Error scheduling cleanup: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to schedule cleanup: {str(e)}"
        )


@router.get("/templates")
async def list_templates(
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    List available report templates.
    
    Args:
        current_user: Current user
    
    Returns:
        List of templates
    """
    try:
        return template_manager.list_templates()
        
    except Exception as e:
        logger.error(f"Error listing templates: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list templates: {str(e)}"
        )


@router.post("/templates")
async def create_template(
    template_data: Dict[str, Any],
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Create a new report template.
    
    Args:
        template_data: Template configuration
        current_user: Current user
    
    Returns:
        Template creation result
    """
    try:
        # Check permissions (admin only for template creation)
        if not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can create templates"
            )
        
        result = template_manager.create_template(template_data)
        return result
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating template: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create template: {str(e)}"
        )


@router.delete("/templates/{template_name}")
async def delete_template(
    template_name: str,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Delete a report template.
    
    Args:
        template_name: Template name
        current_user: Current user
    
    Returns:
        Deletion result
    """
    try:
        # Check permissions
        if not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can delete templates"
            )
        
        result = template_manager.delete_template(template_name)
        return result
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error deleting template: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete template: {str(e)}"
        )