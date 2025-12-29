import pandas as pd
from celery import shared_task
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime

from shared.database.session import get_session
from shared.models.rule_models import Rule
from shared.models.file_models import File, FileStatus
from shared.models.finding_models import Finding
from shared.messaging.event_publisher import event_publisher
from shared.utils.logging import logger

from services.rule_engine.evaluator.bulk_processor import bulk_processor


@shared_task(bind=True, max_retries=3)
def evaluate_rules_task(self, file_id: str, tenant_id: str):
    """
    Evaluate rules against a processed file.
    
    Args:
        file_id: File ID
        tenant_id: Tenant ID
    """
    file_uuid = UUID(file_id)
    tenant_uuid = UUID(tenant_id)
    
    logger.info(f"Evaluating rules for file: {file_id}", tenant_id=tenant_id)
    
    with get_session() as db:
        # Get file
        db_file = db.query(File).filter(
            File.id == file_uuid,
            File.tenant_id == tenant_uuid
        ).first()
        
        if not db_file:
            logger.error(f"File not found: {file_id}", tenant_id=tenant_id)
            raise ValueError(f"File not found: {file_id}")
        
        if db_file.status != FileStatus.PROCESSED:
            logger.error(f"File not processed: {file_id}", tenant_id=tenant_id)
            raise ValueError(f"File not processed: {file_id}")
        
        try:
            # Get active rules for tenant
            rules = db.query(Rule).filter(
                Rule.tenant_id == tenant_uuid,
                Rule.is_active == True
            ).all()
            
            if not rules:
                logger.warning(f"No active rules found for tenant", tenant_id=tenant_id)
                return {
                    "status": "skipped",
                    "message": "No active rules found",
                    "file_id": file_id
                }
            
            logger.info(f"Found {len(rules)} active rules for evaluation", tenant_id=tenant_id)
            
            # Process file with rules
            findings = bulk_processor.process_file(
                rules=rules,
                file_path=db_file.storage_path,
                file_id=file_uuid,
                file_type=db_file.file_type.lstrip('.')
            )
            
            # Save findings to database
            saved_count = 0
            for finding_data in findings:
                finding = Finding(
                    tenant_id=tenant_uuid,
                    rule_id=UUID(finding_data["rule_id"]),
                    file_id=file_uuid,
                    severity=finding_data["severity"],
                    description=finding_data["description"],
                    raw_data=finding_data["raw_data"],
                    context=finding_data.get("context"),
                    location=finding_data.get("location"),
                    status="open"
                )
                
                db.add(finding)
                saved_count += 1
            
            db.commit()
            
            # Generate summary
            summary = bulk_processor.generate_summary_report(findings)
            
            logger.info(
                f"Rule evaluation completed: {saved_count} findings",
                tenant_id=tenant_id,
                file_id=file_id,
                summary=summary
            )
            
            # Publish evaluation complete event
            event_publisher.publish(
                queue_name="findings_generated",
                message_type="rule.evaluation.complete",
                source_service="worker_service",
                payload={
                    "tenant_id": tenant_id,
                    "file_id": file_id,
                    "findings_count": saved_count,
                    "summary": summary
                },
                tenant_id=tenant_uuid
            )
            
            return {
                "status": "success",
                "file_id": file_id,
                "rules_evaluated": len(rules),
                "findings_generated": saved_count,
                "summary": summary
            }
            
        except Exception as e:
            logger.error(f"Error evaluating rules: {str(e)}", tenant_id=tenant_id)
            
            # Retry the task
            raise self.retry(exc=e, countdown=60)


@shared_task
def cleanup_old_results():
    """Clean up old evaluation results."""
    from datetime import datetime, timedelta
    
    with get_session() as db:
        # Delete findings older than 90 days
        cutoff_date = datetime.utcnow() - timedelta(days=90)
        
        deleted_count = db.query(Finding).filter(
            Finding.created_at < cutoff_date,
            Finding.status.in_(["resolved", "false_positive"])
        ).delete(synchronize_session=False)
        
        db.commit()
        
        logger.info(f"Cleaned up {deleted_count} old findings")
        
        return {"deleted_count": deleted_count}


@shared_task(bind=True)
def evaluate_specific_rules_task(self, file_id: str, tenant_id: str, rule_ids: list):
    """
    Evaluate specific rules against a file.
    
    Args:
        file_id: File ID
        tenant_id: Tenant ID
        rule_ids: List of rule IDs to evaluate
    """
    file_uuid = UUID(file_id)
    tenant_uuid = UUID(tenant_id)
    rule_uuids = [UUID(rid) for rid in rule_ids]
    
    logger.info(
        f"Evaluating specific rules for file: {file_id}",
        tenant_id=tenant_id,
        rule_ids=rule_ids
    )
    
    with get_session() as db:
        # Get file
        db_file = db.query(File).filter(
            File.id == file_uuid,
            File.tenant_id == tenant_uuid
        ).first()
        
        if not db_file:
            logger.error(f"File not found: {file_id}", tenant_id=tenant_id)
            raise ValueError(f"File not found: {file_id}")
        
        if db_file.status != FileStatus.PROCESSED:
            logger.error(f"File not processed: {file_id}", tenant_id=tenant_id)
            raise ValueError(f"File not processed: {file_id}")
        
        try:
            # Get specific rules
            rules = db.query(Rule).filter(
                Rule.tenant_id == tenant_uuid,
                Rule.id.in_(rule_uuids),
                Rule.is_active == True
            ).all()
            
            if not rules:
                logger.warning(f"No matching active rules found", tenant_id=tenant_id)
                return {
                    "status": "skipped",
                    "message": "No matching active rules found",
                    "file_id": file_id
                }
            
            logger.info(f"Found {len(rules)} rules for evaluation", tenant_id=tenant_id)
            
            # Process file with rules
            findings = bulk_processor.process_file(
                rules=rules,
                file_path=db_file.storage_path,
                file_id=file_uuid,
                file_type=db_file.file_type.lstrip('.')
            )
            
            # Save findings to database
            saved_count = 0
            for finding_data in findings:
                finding = Finding(
                    tenant_id=tenant_uuid,
                    rule_id=UUID(finding_data["rule_id"]),
                    file_id=file_uuid,
                    severity=finding_data["severity"],
                    description=finding_data["description"],
                    raw_data=finding_data["raw_data"],
                    context=finding_data.get("context"),
                    location=finding_data.get("location"),
                    status="open"
                )
                
                db.add(finding)
                saved_count += 1
            
            db.commit()
            
            logger.info(
                f"Specific rule evaluation completed: {saved_count} findings",
                tenant_id=tenant_id,
                file_id=file_id
            )
            
            return {
                "status": "success",
                "file_id": file_id,
                "rules_evaluated": len(rules),
                "findings_generated": saved_count
            }
            
        except Exception as e:
            logger.error(f"Error evaluating specific rules: {str(e)}", tenant_id=tenant_id)
            raise