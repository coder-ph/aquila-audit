"""
Celery tasks for report generation.
"""
import json
from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime
from pathlib import Path

from celery.utils.log import get_task_logger
from sqlalchemy.orm import Session

from services.worker_service.celery_app import celery_app
from shared.database.session import get_db
from shared.models.report_models import Report
from shared.models.finding_models import Finding
from shared.models.rule_models import Rule
from shared.messaging.message_formats import (
    MessageType,
    ReportGenerationMessage,
    create_message,
    validate_message
)
from shared.messaging.rabbitmq_client import rabbitmq_client
from shared.utils.logging import logger as shared_logger
from shared.utils.config import settings
from services.reporting_service.generators.report_generator import report_generator
from services.reporting_service.security.signature.digital_signer import digital_signer
from services.llm_service.clients.openai_client import llm_client

# Get task logger
logger = get_task_logger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def generate_report_task(
    self,
    report_data: Dict[str, Any],
    message: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Celery task for generating reports asynchronously.
    
    Args:
        report_data: Report generation data
        message: Original RabbitMQ message (if triggered by message queue)
    
    Returns:
        Report generation result
    """
    task_id = self.request.id
    logger.info(f"Starting report generation task {task_id}")
    
    try:
        # Extract parameters
        tenant_id = report_data.get('tenant_id')
        report_id = report_data.get('report_id')
        report_type = report_data.get('report_type', 'pdf')
        findings_ids = report_data.get('findings_ids', [])
        user_id = report_data.get('user_id')
        include_explanations = report_data.get('include_explanations', False)
        
        if not all([tenant_id, report_id, user_id]):
            raise ValueError("Missing required parameters: tenant_id, report_id, user_id")
        
        # Get database session
        db: Session = next(get_db())
        
        # Fetch findings data
        findings_data = fetch_findings_data(db, findings_ids, tenant_id)
        
        # Add AI explanations if requested
        if include_explanations and findings_data:
            findings_data = add_ai_explanations(findings_data, tenant_id)
        
        # Prepare report data
        full_report_data = {
            **report_data,
            'findings': findings_data,
            'generated_at': datetime.utcnow().isoformat(),
            'task_id': task_id,
            'report_metadata': {
                'tenant_id': tenant_id,
                'report_id': report_id,
                'format': report_type,
                'total_findings': len(findings_data),
                'include_explanations': include_explanations
            }
        }
        
        # Generate report
        result = report_generator.generate_report(
            report_data=full_report_data,
            output_format=report_type,
            tenant_id=tenant_id
        )
        
        # Add digital signature if enabled
        if settings.enable_digital_signatures and result.get('success', False):
            report_path = result.get('output_path')
            if report_path:
                signature = digital_signer.sign_report(report_path)
                result['signature'] = signature
                result['signed_at'] = datetime.utcnow().isoformat()
        
        # Update report status in database
        update_report_status(db, report_id, 'completed', result)
        
        # Publish completion message
        publish_report_completion(
            tenant_id=tenant_id,
            report_id=report_id,
            result=result,
            user_id=user_id
        )
        
        logger.info(f"Report generation task {task_id} completed successfully")
        
        return {
            'success': True,
            'task_id': task_id,
            'report_id': report_id,
            'result': result
        }
        
    except Exception as exc:
        logger.error(f"Report generation task {task_id} failed: {str(exc)}")
        
        # Update report status to failed
        try:
            db: Session = next(get_db())
            update_report_status(db, report_data.get('report_id'), 'failed', {'error': str(exc)})
        except Exception as db_error:
            logger.error(f"Failed to update report status: {str(db_error)}")
        
        # Publish failure message
        publish_report_failure(
            tenant_id=report_data.get('tenant_id'),
            report_id=report_data.get('report_id'),
            error=str(exc),
            user_id=report_data.get('user_id')
        )
        
        # Retry the task
        raise self.retry(exc=exc)


@celery_app.task(bind=True)
def generate_batch_reports_task(
    self,
    batch_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate multiple reports in batch.
    
    Args:
        batch_data: Batch generation data
    
    Returns:
        Batch generation results
    """
    task_id = self.request.id
    tenant_id = batch_data.get('tenant_id')
    user_id = batch_data.get('user_id')
    reports_config = batch_data.get('reports', [])
    
    logger.info(f"Starting batch report generation task {task_id} for tenant {tenant_id}")
    
    results = []
    successful = 0
    failed = 0
    
    for report_config in reports_config:
        try:
            # Create individual report task
            report_data = {
                **report_config,
                'tenant_id': tenant_id,
                'user_id': user_id,
                'batch_task_id': task_id
            }
            
            # Generate report as subtask
            result = generate_report_task.apply_async(
                args=[report_data],
                queue='report_generation'
            )
            
            results.append({
                'report_id': report_config.get('report_id'),
                'task_id': result.id,
                'status': 'queued'
            })
            
        except Exception as e:
            logger.error(f"Failed to queue report {report_config.get('report_id')}: {str(e)}")
            results.append({
                'report_id': report_config.get('report_id'),
                'error': str(e),
                'status': 'failed'
            })
            failed += 1
    
    return {
        'batch_task_id': task_id,
        'tenant_id': tenant_id,
        'total_reports': len(reports_config),
        'queued': len(reports_config) - failed,
        'failed': failed,
        'results': results
    }


@celery_app.task
def cleanup_generated_reports(
    max_age_days: Optional[int] = None,
    tenant_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Clean up old generated reports.
    
    Args:
        max_age_days: Maximum age in days
        tenant_id: Tenant ID
    
    Returns:
        Cleanup statistics
    """
    logger.info(f"Starting report cleanup for tenant: {tenant_id}")
    
    result = report_generator.cleanup_old_reports(
        max_age_days=max_age_days,
        tenant_id=tenant_id
    )
    
    logger.info(f"Report cleanup completed: {result}")
    
    return result


def fetch_findings_data(
    db: Session,
    findings_ids: list[str],
    tenant_id: str
) -> list[Dict[str, Any]]:
    """
    Fetch findings data from database.
    
    Args:
        db: Database session
        findings_ids: List of finding IDs
        tenant_id: Tenant ID
    
    Returns:
        List of finding data
    """
    if not findings_ids:
        return []
    
    # Query findings
    findings = db.query(Finding).filter(
        Finding.id.in_(findings_ids),
        Finding.tenant_id == tenant_id
    ).all()
    
    findings_data = []
    
    for finding in findings:
        # Get rule information
        rule = db.query(Rule).filter(Rule.id == finding.rule_id).first()
        
        finding_dict = {
            'id': str(finding.id),
            'title': finding.title,
            'description': finding.description,
            'severity': finding.severity,
            'category': finding.category,
            'source_file': finding.source_file,
            'line_number': finding.line_number,
            'detected_at': finding.detected_at.isoformat() if finding.detected_at else None,
            'status': finding.status,
            'evidence': finding.evidence,
            'recommendation': finding.recommendation,
            'rule': {
                'id': str(rule.id) if rule else None,
                'name': rule.name if rule else None,
                'category': rule.category if rule else None,
                'description': rule.description if rule else None
            } if rule else None
        }
        
        findings_data.append(finding_dict)
    
    return findings_data


def add_ai_explanations(
    findings_data: list[Dict[str, Any]],
    tenant_id: str
) -> list[Dict[str, Any]]:
    """
    Add AI explanations to findings.
    
    Args:
        findings_data: List of finding data
        tenant_id: Tenant ID
    
    Returns:
        Findings data with AI explanations
    """
    if not findings_data:
        return findings_data
    
    # Group findings by severity for batch processing
    findings_by_severity = {}
    for finding in findings_data:
        severity = finding.get('severity', 'medium')
        if severity not in findings_by_severity:
            findings_by_severity[severity] = []
        findings_by_severity[severity].append(finding)
    
    # Add AI explanations
    for severity, findings in findings_by_severity.items():
        for finding in findings:
            try:
                # Generate explanation using LLM
                explanation_prompt = f"""
                Finding: {finding.get('title')}
                Description: {finding.get('description')}
                Severity: {finding.get('severity')}
                Category: {finding.get('category')}
                
                Please provide:
                1. A simple explanation of this finding
                2. Why it matters
                3. Common root causes
                4. Best practices to address it
                """
                
                explanation = llm_client.generate_explanation(
                    prompt=explanation_prompt,
                    context=f"Finding analysis for tenant {tenant_id}",
                    max_tokens=300
                )
                
                finding['ai_explanation'] = explanation
                
            except Exception as e:
                logger.warning(f"Failed to generate AI explanation for finding {finding.get('id')}: {str(e)}")
                finding['ai_explanation'] = "AI explanation not available."
    
    return findings_data


def update_report_status(
    db: Session,
    report_id: str,
    status: str,
    result: Dict[str, Any]
) -> None:
    """
    Update report status in database.
    
    Args:
        db: Database session
        report_id: Report ID
        status: New status
        result: Generation result
    """
    try:
        report = db.query(Report).filter(Report.id == report_id).first()
        
        if report:
            report.status = status
            report.generated_at = datetime.utcnow() if status == 'completed' else None
            report.result_data = result
            
            if status == 'completed' and 'output_path' in result:
                report.file_path = result['output_path']
            
            db.commit()
            logger.info(f"Updated report {report_id} status to {status}")
    
    except Exception as e:
        logger.error(f"Failed to update report status for {report_id}: {str(e)}")
        db.rollback()


def publish_report_completion(
    tenant_id: str,
    report_id: str,
    result: Dict[str, Any],
    user_id: str
) -> None:
    """
    Publish report completion message.
    
    Args:
        tenant_id: Tenant ID
        report_id: Report ID
        result: Generation result
        user_id: User ID
    """
    try:
        message = create_message(
            message_type=MessageType.REPORT_GENERATION_COMPLETE,
            source_service="reporting_service",
            payload={
                'tenant_id': tenant_id,
                'report_id': report_id,
                'status': 'completed',
                'result': result,
                'user_id': user_id,
                'completed_at': datetime.utcnow().isoformat()
            }
        )
        
        rabbitmq_client.publish_message(
            queue_name='report_generation_complete',
            message=message,
            tenant_id=tenant_id,
            priority=5
        )
        
        logger.info(f"Published report completion message for report {report_id}")
    
    except Exception as e:
        logger.error(f"Failed to publish report completion message: {str(e)}")


def publish_report_failure(
    tenant_id: str,
    report_id: str,
    error: str,
    user_id: str
) -> None:
    """
    Publish report failure message.
    
    Args:
        tenant_id: Tenant ID
        report_id: Report ID
        error: Error message
        user_id: User ID
    """
    try:
        message = create_message(
            message_type=MessageType.TASK_FAILED,
            source_service="reporting_service",
            payload={
                'tenant_id': tenant_id,
                'task_id': f"report_generation_{report_id}",
                'task_type': 'report_generation',
                'error_message': error,
                'user_id': user_id,
                'failed_at': datetime.utcnow().isoformat()
            }
        )
        
        rabbitmq_client.publish_message(
            queue_name='task_failed',
            message=message,
            tenant_id=tenant_id,
            priority=9  # High priority for failures
        )
        
        logger.error(f"Published report failure message for report {report_id}")
    
    except Exception as e:
        logger.error(f"Failed to publish report failure message: {str(e)}")