"""
Admin dashboard API routes.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from shared.auth.middleware import get_current_user
from shared.models.user_models import User
from shared.utils.logging import logger

from services.admin_service.dependencies.auth import verify_admin_token
from services.admin_service.dashboards.usage_dashboard import usage_dashboard

# Create router
router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(verify_admin_token)]
)


@router.get("/overview")
async def get_dashboard_overview(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get dashboard overview statistics.
    
    Args:
        current_user: Current user
    
    Returns:
        Dashboard overview
    """
    try:
        overview = usage_dashboard.get_overview_stats()
        return overview
        
    except Exception as e:
        logger.error(f"Error getting dashboard overview: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get dashboard overview: {str(e)}"
        )


@router.get("/usage-ranking")
async def get_usage_ranking(
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Get tenant usage ranking.
    
    Args:
        limit: Number of tenants to return
        current_user: Current user
    
    Returns:
        Tenant usage ranking
    """
    try:
        ranking = usage_dashboard.get_tenant_usage_ranking(limit)
        return ranking
        
    except Exception as e:
        logger.error(f"Error getting usage ranking: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get usage ranking: {str(e)}"
        )


@router.get("/plan-distribution")
async def get_plan_distribution(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get billing plan distribution.
    
    Args:
        current_user: Current user
    
    Returns:
        Plan distribution
    """
    try:
        distribution = usage_dashboard.get_plan_distribution()
        return distribution
        
    except Exception as e:
        logger.error(f"Error getting plan distribution: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get plan distribution: {str(e)}"
        )


@router.get("/alerts")
async def get_alerts_summary(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get alerts summary.
    
    Args:
        current_user: Current user
    
    Returns:
        Alerts summary
    """
    try:
        alerts = usage_dashboard.get_active_alerts_summary()
        return alerts
        
    except Exception as e:
        logger.error(f"Error getting alerts summary: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get alerts summary: {str(e)}"
        )


@router.get("/tenant/{tenant_id}/analytics")
async def get_tenant_analytics(
    tenant_id: str,
    timeframe: str = Query("month", regex="^(day|week|month|year)$"),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get detailed analytics for a tenant.
    
    Args:
        tenant_id: Tenant ID
        timeframe: Timeframe for analytics
        current_user: Current user
    
    Returns:
        Tenant analytics
    """
    try:
        from shared.database.session import get_db
        from shared.models.user_models import Tenant
        from shared.models.billing_models import UsageRecord, Subscription
        from sqlalchemy import func
        from uuid import UUID
        
        db = next(get_db())
        
        # Get tenant
        tenant = db.query(Tenant).filter(Tenant.id == UUID(tenant_id)).first()
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found"
            )
        
        # Calculate timeframe
        end_date = datetime.now()
        if timeframe == "day":
            start_date = end_date - timedelta(days=1)
        elif timeframe == "week":
            start_date = end_date - timedelta(weeks=1)
        elif timeframe == "month":
            start_date = end_date - timedelta(days=30)
        else:  # year
            start_date = end_date - timedelta(days=365)
        
        # Get usage data
        usage_data = db.query(
            UsageRecord.metric_name,
            func.sum(UsageRecord.metric_value).label('total')
        ).filter(
            UsageRecord.tenant_id == UUID(tenant_id),
            UsageRecord.recorded_at >= start_date,
            UsageRecord.recorded_at <= end_date
        ).group_by(UsageRecord.metric_name).all()
        
        usage = {metric: total for metric, total in usage_data}
        
        # Get subscription info
        subscription = db.query(Subscription).filter(
            Subscription.tenant_id == UUID(tenant_id),
            Subscription.status == 'active'
        ).first()
        
        # Calculate growth
        previous_start = start_date - (end_date - start_date)
        previous_usage = db.query(
            UsageRecord.metric_name,
            func.sum(UsageRecord.metric_value).label('total')
        ).filter(
            UsageRecord.tenant_id == UUID(tenant_id),
            UsageRecord.recorded_at >= previous_start,
            UsageRecord.recorded_at <= start_date
        ).group_by(UsageRecord.metric_name).all()
        
        previous = {metric: total for metric, total in previous_usage}
        
        # Calculate growth percentages
        growth = {}
        for metric in set(usage.keys()) | set(previous.keys()):
            current = usage.get(metric, 0)
            previous_val = previous.get(metric, 0)
            
            if previous_val == 0:
                growth_percent = 100 if current > 0 else 0
            else:
                growth_percent = ((current - previous_val) / previous_val) * 100
            
            growth[metric] = {
                'current': current,
                'previous': previous_val,
                'growth': growth_percent,
                'trend': 'up' if growth_percent > 0 else 'down' if growth_percent < 0 else 'stable'
            }
        
        return {
            'tenant_id': tenant_id,
            'tenant_name': tenant.name,
            'tenant_slug': tenant.slug,
            'timeframe': timeframe,
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'usage': usage,
            'growth': growth,
            'subscription': {
                'plan_name': subscription.billing_plan.name if subscription else 'Free',
                'status': subscription.status if subscription else 'active',
                'is_trial': subscription.is_trial if subscription else False
            },
            'user_count': len(tenant.users),
            'is_active': tenant.is_active,
            'created_at': tenant.created_at.isoformat() if tenant.created_at else None
        }
        
    except Exception as e:
        logger.error(f"Error getting tenant analytics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get tenant analytics: {str(e)}"
        )


@router.get("/revenue")
async def get_revenue_analytics(
    period: str = Query("month", regex="^(day|week|month|year)$"),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get revenue analytics.
    
    Args:
        period: Time period
        current_user: Current user
    
    Returns:
        Revenue analytics
    """
    try:
        from shared.database.session import get_db
        from shared.models.billing_models import Invoice
        from sqlalchemy import func
        
        db = next(get_db())
        
        # Calculate timeframe
        end_date = datetime.now()
        if period == "day":
            start_date = end_date - timedelta(days=1)
            group_by = 'hour'
        elif period == "week":
            start_date = end_date - timedelta(weeks=1)
            group_by = 'day'
        elif period == "month":
            start_date = end_date - timedelta(days=30)
            group_by = 'day'
        else:  # year
            start_date = end_date - timedelta(days=365)
            group_by = 'month'
        
        # Build grouping expression
        if group_by == 'hour':
            group_expr = func.date_trunc('hour', Invoice.paid_at)
        elif group_by == 'day':
            group_expr = func.date_trunc('day', Invoice.paid_at)
        else:  # month
            group_expr = func.date_trunc('month', Invoice.paid_at)
        
        # Query revenue data
        revenue_data = db.query(
            group_expr.label('period'),
            func.sum(Invoice.amount).label('revenue'),
            func.count(Invoice.id).label('invoice_count')
        ).filter(
            Invoice.status == 'paid',
            Invoice.paid_at >= start_date,
            Invoice.paid_at <= end_date
        ).group_by(group_expr).order_by(group_expr).all()
        
        # Format results
        periods = []
        revenue = []
        invoice_counts = []
        
        for period_time, period_revenue, count in revenue_data:
            periods.append(period_time.isoformat())
            revenue.append(float(period_revenue) if period_revenue else 0)
            invoice_counts.append(count)
        
        # Calculate totals
        total_revenue = sum(revenue)
        total_invoices = sum(invoice_counts)
        
        # Calculate average invoice value
        avg_invoice = total_revenue / total_invoices if total_invoices > 0 else 0
        
        return {
            'period': period,
            'time_range': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'data': {
                'periods': periods,
                'revenue': revenue,
                'invoice_counts': invoice_counts
            },
            'totals': {
                'revenue': total_revenue,
                'invoice_count': total_invoices,
                'average_invoice': avg_invoice
            },
            'currency': 'USD'
        }
        
    except Exception as e:
        logger.error(f"Error getting revenue analytics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get revenue analytics: {str(e)}"
        )