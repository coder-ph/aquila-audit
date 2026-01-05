"""
Usage tracking API routes.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timedelta

from shared.auth.middleware import get_current_user, verify_tenant_access
from shared.models.user_models import User
from shared.utils.logging import logger

from services.billing_service.config import config
from services.billing_service.tracking.usage_tracker import usage_tracker

# Create router
router = APIRouter(
    prefix="",
    tags=["usage"],
    dependencies=[Depends(get_current_user)]
)


@router.get("/current")
async def get_current_usage(
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get current usage for tenant.
    
    Args:
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        Current usage summary
    """
    try:
        usage_summary = usage_tracker.get_usage_summary(UUID(tenant_id))
        
        return {
            'tenant_id': tenant_id,
            'timestamp': datetime.now().isoformat(),
            'usage': usage_summary
        }
        
    except Exception as e:
        logger.error(f"Error getting current usage: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get current usage: {str(e)}"
        )


@router.get("/history")
async def get_usage_history(
    tenant_id: str = Depends(verify_tenant_access),
    timeframe: str = Query("month", regex="^(day|week|month|year)$"),
    metric: Optional[str] = None,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get usage history for tenant.
    
    Args:
        tenant_id: Tenant ID
        timeframe: Timeframe for history
        metric: Specific metric to filter
        current_user: Current user
    
    Returns:
        Usage history
    """
    try:
        usage_data = usage_tracker.get_tenant_usage(
            tenant_id=UUID(tenant_id),
            timeframe=timeframe
        )
        
        # Filter by metric if specified
        if metric and 'historical_data' in usage_data:
            if metric in usage_data['historical_data']:
                usage_data['historical_data'] = {
                    metric: usage_data['historical_data'][metric]
                }
            else:
                usage_data['historical_data'] = {}
        
        return usage_data
        
    except Exception as e:
        logger.error(f"Error getting usage history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get usage history: {str(e)}"
        )


@router.get("/limits")
async def get_usage_limits(
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get usage limits for tenant.
    
    Args:
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        Usage limits
    """
    try:
        from shared.database.session import get_db
        from shared.models.billing_models import Subscription
        
        db = next(get_db())
        
        # Get subscription
        subscription = db.query(Subscription).filter(
            Subscription.tenant_id == UUID(tenant_id),
            Subscription.status == 'active'
        ).first()
        
        if not subscription:
            # Return free tier limits
            return {
                'tenant_id': tenant_id,
                'plan_name': 'Free',
                'limits': {
                    'max_users': 1,
                    'max_storage_gb': 1,
                    'max_files_per_month': 100,
                    'max_api_calls': 1000
                },
                'is_trial': False,
                'trial_ends_at': None
            }
        
        plan = subscription.billing_plan
        
        return {
            'tenant_id': tenant_id,
            'subscription_id': str(subscription.id),
            'plan_name': plan.name,
            'limits': {
                'max_users': plan.max_users,
                'max_storage_gb': plan.max_storage_gb,
                'max_files_per_month': plan.max_files_per_month,
                'max_api_calls': plan.max_api_calls
            },
            'is_trial': subscription.is_trial,
            'trial_ends_at': subscription.trial_ends_at.isoformat() if subscription.trial_ends_at else None,
            'current_period_end': subscription.current_period_end.isoformat() if subscription.current_period_end else None
        }
        
    except Exception as e:
        logger.error(f"Error getting usage limits: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get usage limits: {str(e)}"
        )


@router.get("/breakdown")
async def get_usage_breakdown(
    tenant_id: str = Depends(verify_tenant_access),
    group_by: str = Query("day", regex="^(hour|day|week|month)$"),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get usage breakdown by time period.
    
    Args:
        tenant_id: Tenant ID
        group_by: Time grouping
        current_user: Current user
    
    Returns:
        Usage breakdown
    """
    try:
        # Calculate time range based on grouping
        end_date = datetime.now()
        if group_by == 'hour':
            start_date = end_date - timedelta(days=1)
        elif group_by == 'day':
            start_date = end_date - timedelta(days=30)
        elif group_by == 'week':
            start_date = end_date - timedelta(weeks=12)
        elif group_by == 'month':
            start_date = end_date - timedelta(days=365)
        
        # Get usage data
        from shared.database.session import get_db
        from shared.models.billing_models import UsageRecord
        from sqlalchemy import func, extract
        
        db = next(get_db())
        
        # Build grouping expression
        if group_by == 'hour':
            group_expr = func.date_trunc('hour', UsageRecord.recorded_at)
        elif group_by == 'day':
            group_expr = func.date_trunc('day', UsageRecord.recorded_at)
        elif group_by == 'week':
            group_expr = func.date_trunc('week', UsageRecord.recorded_at)
        else:  # month
            group_expr = func.date_trunc('month', UsageRecord.recorded_at)
        
        # Query usage records
        results = db.query(
            group_expr.label('period'),
            UsageRecord.metric_name,
            func.sum(UsageRecord.metric_value).label('total')
        ).filter(
            UsageRecord.tenant_id == UUID(tenant_id),
            UsageRecord.recorded_at >= start_date,
            UsageRecord.recorded_at <= end_date
        ).group_by(
            group_expr, UsageRecord.metric_name
        ).order_by(
            group_expr, UsageRecord.metric_name
        ).all()
        
        # Organize data
        breakdown = {}
        for period, metric_name, total in results:
            period_str = period.isoformat()
            if period_str not in breakdown:
                breakdown[period_str] = {}
            
            breakdown[period_str][metric_name] = total
        
        return {
            'tenant_id': tenant_id,
            'group_by': group_by,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'breakdown': breakdown
        }
        
    except Exception as e:
        logger.error(f"Error getting usage breakdown: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get usage breakdown: {str(e)}"
        )


@router.get("/comparison")
async def get_usage_comparison(
    tenant_id: str = Depends(verify_tenant_access),
    period1_start: str = Query(..., description="First period start (ISO format)"),
    period1_end: str = Query(..., description="First period end (ISO format)"),
    period2_start: str = Query(..., description="Second period start (ISO format)"),
    period2_end: str = Query(..., description="Second period end (ISO format)"),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Compare usage between two periods.
    
    Args:
        tenant_id: Tenant ID
        period1_start: First period start
        period1_end: First period end
        period2_start: Second period start
        period2_end: Second period end
        current_user: Current user
    
    Returns:
        Usage comparison
    """
    try:
        # Parse dates
        p1_start = datetime.fromisoformat(period1_start)
        p1_end = datetime.fromisoformat(period1_end)
        p2_start = datetime.fromisoformat(period2_start)
        p2_end = datetime.fromisoformat(period2_end)
        
        # Get usage for both periods
        from shared.database.session import get_db
        from shared.models.billing_models import UsageRecord
        from sqlalchemy import func
        
        db = next(get_db())
        
        def get_period_usage(start_date, end_date):
            results = db.query(
                UsageRecord.metric_name,
                func.sum(UsageRecord.metric_value).label('total')
            ).filter(
                UsageRecord.tenant_id == UUID(tenant_id),
                UsageRecord.recorded_at >= start_date,
                UsageRecord.recorded_at <= end_date
            ).group_by(UsageRecord.metric_name).all()
            
            return {metric: total for metric, total in results}
        
        period1_usage = get_period_usage(p1_start, p1_end)
        period2_usage = get_period_usage(p2_start, p2_end)
        
        # Calculate comparison
        all_metrics = set(period1_usage.keys()) | set(period2_usage.keys())
        
        comparison = {}
        for metric in all_metrics:
            p1_value = period1_usage.get(metric, 0)
            p2_value = period2_usage.get(metric, 0)
            
            if p1_value == 0:
                change_percentage = 100 if p2_value > 0 else 0
            else:
                change_percentage = ((p2_value - p1_value) / p1_value) * 100
            
            comparison[metric] = {
                'period1': p1_value,
                'period2': p2_value,
                'change': p2_value - p1_value,
                'change_percentage': change_percentage,
                'trend': 'increase' if p2_value > p1_value else 'decrease' if p2_value < p1_value else 'stable'
            }
        
        return {
            'tenant_id': tenant_id,
            'period1': {
                'start': period1_start,
                'end': period1_end,
                'days': (p1_end - p1_start).days
            },
            'period2': {
                'start': period2_start,
                'end': period2_end,
                'days': (p2_end - p2_start).days
            },
            'comparison': comparison
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error getting usage comparison: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get usage comparison: {str(e)}"
        )