from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.orm import Session
from uuid import UUID

from shared.database.session import get_session
from shared.models.schemas import (
    RuleCreate,
    RuleUpdate,
    RuleResponse,
    PaginatedResponse
)
from shared.models.rule_models import Rule, RuleSet
from shared.utils.logging import logger

from services.rule_engine.dependencies.auth import get_current_user_with_tenant
from services.rule_engine.evaluator.jsonata_engine import jsonata_engine

# Create router
router = APIRouter()


@router.post("/", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    rule: RuleCreate,
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session)
):
    """
    Create a new rule.
    """
    user_id, tenant_id = user_info
    
    # Validate JSONata expression
    is_valid, error_message = jsonata_engine.validate_expression(rule.rule_expression)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid rule expression: {error_message}"
        )
    
    # Check if rule with same name exists in tenant
    existing_rule = db.query(Rule).filter(
        Rule.tenant_id == tenant_id,
        Rule.name == rule.name
    ).first()
    
    if existing_rule:
        raise HTTPException(
            status_code=status.HTTP_400_BADREQUEST,
            detail=f"Rule with name '{rule.name}' already exists in this tenant"
        )
    
    # Create rule
    db_rule = Rule(
        tenant_id=tenant_id,
        name=rule.name,
        description=rule.description,
        rule_type=rule.rule_type,
        rule_expression=rule.rule_expression,
        severity=rule.severity,
        is_active=rule.is_active,
        category=rule.category,
        tags=rule.tags,
        created_by_user_id=user_id
    )
    
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    
    logger.info(f"Rule created: {rule.name}", tenant_id=str(tenant_id))
    
    return db_rule


@router.get("/", response_model=PaginatedResponse)
async def list_rules(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    is_active: Optional[bool] = None,
    rule_type: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session)
):
    """
    List rules for current tenant.
    """
    user_id, tenant_id = user_info
    
    # Build query
    query = db.query(Rule).filter(Rule.tenant_id == tenant_id)
    
    # Apply filters
    if is_active is not None:
        query = query.filter(Rule.is_active == is_active)
    
    if rule_type:
        query = query.filter(Rule.rule_type == rule_type)
    
    if category:
        query = query.filter(Rule.category == category)
    
    if search:
        query = query.filter(
            (Rule.name.ilike(f"%{search}%")) | 
            (Rule.description.ilike(f"%{search}%")) |
            (Rule.rule_expression.ilike(f"%{search}%"))
        )
    
    # Get total count
    total = query.count()
    
    # Get paginated results
    rules = query.order_by(Rule.created_at.desc()).offset(skip).limit(limit).all()
    
    return {
        "items": rules,
        "total": total,
        "page": skip // limit + 1,
        "page_size": limit,
        "total_pages": (total + limit - 1) // limit
    }


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(
    rule_id: UUID,
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session)
):
    """
    Get rule details.
    """
    user_id, tenant_id = user_info
    
    rule = db.query(Rule).filter(
        Rule.id == rule_id,
        Rule.tenant_id == tenant_id
    ).first()
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found"
        )
    
    return rule


@router.put("/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: UUID,
    rule_update: RuleUpdate,
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session)
):
    """
    Update rule.
    """
    user_id, tenant_id = user_info
    
    db_rule = db.query(Rule).filter(
        Rule.id == rule_id,
        Rule.tenant_id == tenant_id
    ).first()
    
    if not db_rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found"
        )
    
    # Validate expression if provided
    if rule_update.rule_expression:
        is_valid, error_message = jsonata_engine.validate_expression(rule_update.rule_expression)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid rule expression: {error_message}"
            )
    
    # Update fields
    update_data = rule_update.dict(exclude_unset=True)
    
    for field, value in update_data.items():
        if hasattr(db_rule, field):
            setattr(db_rule, field, value)
    
    db.commit()
    db.refresh(db_rule)
    
    logger.info(f"Rule updated: {db_rule.name}", tenant_id=str(tenant_id))
    
    return db_rule


@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: UUID,
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session)
):
    """
    Delete a rule.
    """
    user_id, tenant_id = user_info
    
    db_rule = db.query(Rule).filter(
        Rule.id == rule_id,
        Rule.tenant_id == tenant_id
    ).first()
    
    if not db_rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found"
        )
    
    # Check if rule has findings
    if db_rule.findings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete rule with existing findings. Deactivate it instead."
        )
    
    # Delete rule
    db.delete(db_rule)
    db.commit()
    
    logger.warning(f"Rule deleted: {db_rule.name}", tenant_id=str(tenant_id))
    
    return {"message": "Rule deleted successfully"}


@router.post("/{rule_id}/test")
async def test_rule(
    rule_id: UUID,
    test_data: Dict[str, Any] = Body(...),
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session)
):
    """
    Test a rule with sample data.
    """
    user_id, tenant_id = user_info
    
    rule = db.query(Rule).filter(
        Rule.id == rule_id,
        Rule.tenant_id == tenant_id
    ).first()
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found"
        )
    
    # Test the expression
    test_result = jsonata_engine.test_expression(
        expression=rule.rule_expression,
        test_data=test_data
    )
    
    # Add rule info to result
    test_result["rule"] = {
        "id": str(rule.id),
        "name": rule.name,
        "type": rule.rule_type,
        "severity": rule.severity
    }
    
    return test_result


@router.post("/{rule_id}/activate")
async def activate_rule(
    rule_id: UUID,
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session)
):
    """
    Activate a rule.
    """
    user_id, tenant_id = user_info
    
    rule = db.query(Rule).filter(
        Rule.id == rule_id,
        Rule.tenant_id == tenant_id
    ).first()
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found"
        )
    
    rule.is_active = True
    db.commit()
    
    logger.info(f"Rule activated: {rule.name}", tenant_id=str(tenant_id))
    
    return {"message": "Rule activated successfully"}


@router.post("/{rule_id}/deactivate")
async def deactivate_rule(
    rule_id: UUID,
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session)
):
    """
    Deactivate a rule.
    """
    user_id, tenant_id = user_info
    
    rule = db.query(Rule).filter(
        Rule.id == rule_id,
        Rule.tenant_id == tenant_id
    ).first()
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found"
        )
    
    rule.is_active = False
    db.commit()
    
    logger.info(f"Rule deactivated: {rule.name}", tenant_id=str(tenant_id))
    
    return {"message": "Rule deactivated successfully"}


@router.get("/{rule_id}/usage")
async def get_rule_usage(
    rule_id: UUID,
    days: int = Query(30, ge=1, le=365),
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session)
):
    """
    Get rule usage statistics.
    """
    user_id, tenant_id = user_info
    
    rule = db.query(Rule).filter(
        Rule.id == rule_id,
        Rule.tenant_id == tenant_id
    ).first()
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found"
        )
    
    # Calculate date range
    from datetime import datetime, timedelta
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Get findings for this rule in date range
    from shared.models.finding_models import Finding
    
    findings = db.query(Finding).filter(
        Finding.rule_id == rule_id,
        Finding.tenant_id == tenant_id,
        Finding.created_at >= start_date
    ).all()
    
    # Calculate statistics
    stats = {
        "total_findings": len(findings),
        "by_severity": {},
        "by_status": {},
        "by_day": {}
    }
    
    for finding in findings:
        # Count by severity
        severity = finding.severity
        stats["by_severity"][severity] = stats["by_severity"].get(severity, 0) + 1
        
        # Count by status
        status = finding.status
        stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
        
        # Count by day
        day = finding.created_at.date().isoformat()
        stats["by_day"][day] = stats["by_day"].get(day, 0) + 1
    
    return {
        "rule_id": str(rule_id),
        "rule_name": rule.name,
        "period_days": days,
        "statistics": stats
    }