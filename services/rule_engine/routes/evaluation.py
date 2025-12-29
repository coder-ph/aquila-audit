from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
from uuid import UUID

from shared.database.session import get_session
from shared.models.rule_models import Rule
from shared.models.file_models import File, FileStatus
from shared.models.finding_models import Finding
from shared.utils.logging import logger

from services.rule_engine.dependencies.auth import get_current_user_with_tenant
from services.rule_engine.evaluator.bulk_processor import bulk_processor

# Create router
router = APIRouter()


@router.post("/evaluate/file/{file_id}")
async def evaluate_file_rules(
    file_id: UUID,
    rule_ids: List[UUID] = Body(None, description="Specific rules to evaluate (all if empty)"),
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session)
):
    """
    Evaluate rules against a file.
    """
    user_id, tenant_id = user_info
    
    # Get file
    file = db.query(File).filter(
        File.id == file_id,
        File.tenant_id == tenant_id
    ).first()
    
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    if file.status != FileStatus.PROCESSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be processed before evaluation"
        )
    
    # Get rules
    if rule_ids:
        # Specific rules
        rules = db.query(Rule).filter(
            Rule.tenant_id == tenant_id,
            Rule.id.in_(rule_ids),
            Rule.is_active == True
        ).all()
    else:
        # All active rules
        rules = db.query(Rule).filter(
            Rule.tenant_id == tenant_id,
            Rule.is_active == True
        ).all()
    
    if not rules:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active rules found for evaluation"
        )
    
    logger.info(f"Evaluating {len(rules)} rules against file {file_id}", tenant_id=str(tenant_id))
    
    try:
        # Process file with rules
        findings = bulk_processor.process_file(
            rules=rules,
            file_path=file.storage_path,
            file_id=file_id,
            file_type=file.file_type.lstrip('.')
        )
        
        # Save findings to database
        saved_findings = []
        for finding_data in findings:
            finding = Finding(
                tenant_id=tenant_id,
                rule_id=UUID(finding_data["rule_id"]),
                file_id=file_id,
                severity=finding_data["severity"],
                description=finding_data["description"],
                raw_data=finding_data["raw_data"],
                context=finding_data.get("context"),
                location=finding_data.get("location"),
                status="open"
            )
            
            db.add(finding)
            saved_findings.append(finding)
        
        db.commit()
        
        # Generate summary
        summary = bulk_processor.generate_summary_report(findings)
        
        logger.info(f"Evaluation completed: {len(saved_findings)} findings", tenant_id=str(tenant_id))
        
        return {
            "file_id": str(file_id),
            "rules_evaluated": len(rules),
            "findings_generated": len(saved_findings),
            "summary": summary,
            "findings": [
                {
                    "id": str(finding.id),
                    "rule_id": str(finding.rule_id),
                    "severity": finding.severity,
                    "description": finding.description,
                    "status": finding.status
                }
                for finding in saved_findings
            ]
        }
        
    except Exception as e:
        logger.error(f"Error evaluating file: {str(e)}", tenant_id=str(tenant_id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Evaluation failed: {str(e)}"
        )


@router.post("/evaluate/data")
async def evaluate_data_rules(
    data: List[Dict[str, Any]] = Body(...),
    rule_ids: List[UUID] = Body(None, description="Specific rules to evaluate"),
    file_id: UUID = Body(None, description="Optional file ID for context"),
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session)
):
    """
    Evaluate rules against provided data.
    """
    user_id, tenant_id = user_info
    
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No data provided for evaluation"
        )
    
    # Get rules
    if rule_ids:
        # Specific rules
        rules = db.query(Rule).filter(
            Rule.tenant_id == tenant_id,
            Rule.id.in_(rule_ids),
            Rule.is_active == True
        ).all()
    else:
        # All active rules
        rules = db.query(Rule).filter(
            Rule.tenant_id == tenant_id,
            Rule.is_active == True
        ).all()
    
    if not rules:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active rules found for evaluation"
        )
    
    logger.info(f"Evaluating {len(rules)} rules against {len(data)} records", tenant_id=str(tenant_id))
    
    try:
        # Evaluate rules against data
        findings = bulk_processor.bulk_evaluator.evaluate_rules_against_data(
            rules=rules,
            data=data,
            file_id=file_id or UUID(int=0),  # Use dummy file ID if not provided
            batch_size=1000
        )
        
        # Generate summary (without saving to database)
        summary = bulk_processor.generate_summary_report(findings)
        
        return {
            "records_evaluated": len(data),
            "rules_evaluated": len(rules),
            "findings_generated": len(findings),
            "summary": summary,
            "findings": [
                {
                    "rule_id": str(finding["rule_id"]),
                    "severity": finding["severity"],
                    "description": finding["description"],
                    "raw_data_preview": {k: str(v)[:100] + "..." if len(str(v)) > 100 else v 
                                        for k, v in finding["raw_data"].items()}
                }
                for finding in findings[:100]  # Limit response
            ]
        }
        
    except Exception as e:
        logger.error(f"Error evaluating data: {str(e)}", tenant_id=str(tenant_id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Evaluation failed: {str(e)}"
        )


@router.get("/files/{file_id}/findings")
async def get_file_findings(
    file_id: UUID,
    skip: int = 0,
    limit: int = 100,
    severity: str = None,
    status: str = None,
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session)
):
    """
    Get findings for a file.
    """
    user_id, tenant_id = user_info
    
    # Check file exists and belongs to tenant
    file = db.query(File).filter(
        File.id == file_id,
        File.tenant_id == tenant_id
    ).first()
    
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    # Build query
    query = db.query(Finding).filter(
        Finding.file_id == file_id,
        Finding.tenant_id == tenant_id
    )
    
    # Apply filters
    if severity:
        query = query.filter(Finding.severity == severity)
    
    if status:
        query = query.filter(Finding.status == status)
    
    # Get total count
    total = query.count()
    
    # Get paginated results
    findings = query.order_by(
        Finding.severity.desc(),
        Finding.created_at.desc()
    ).offset(skip).limit(limit).all()
    
    # Get rule names for findings
    rule_ids = [finding.rule_id for finding in findings]
    rules = db.query(Rule).filter(Rule.id.in_(rule_ids)).all()
    rule_map = {rule.id: rule.name for rule in rules}
    
    # Format response
    findings_data = []
    for finding in findings:
        findings_data.append({
            "id": str(finding.id),
            "rule_id": str(finding.rule_id),
            "rule_name": rule_map.get(finding.rule_id, "Unknown"),
            "severity": finding.severity,
            "description": finding.description,
            "status": finding.status,
            "created_at": finding.created_at.isoformat() if finding.created_at else None,
            "context": finding.context
        })
    
    return {
        "file_id": str(file_id),
        "file_name": file.original_filename,
        "items": findings_data,
        "total": total,
        "page": skip // limit + 1,
        "page_size": limit,
        "total_pages": (total + limit - 1) // limit
    }