"""
Billing API routes.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta

from shared.auth.middleware import get_current_user, verify_tenant_access
from shared.models.user_models import User
from shared.utils.logging import logger

from services.billing_service.config import config
from services.billing_service.tracking.usage_tracker import usage_tracker
from services.billing_service.tracking.cost_calculator import cost_calculator
from services.billing_service.tracking.budget_enforcer import budget_enforcer

# Create router
router = APIRouter(
    prefix="",
    tags=["billing"],
    dependencies=[Depends(get_current_user)]
)


@router.get("/plans")
async def get_billing_plans(
    active_only: bool = Query(True),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Get available billing plans.
    
    Args:
        active_only: Only return active plans
        current_user: Current user
    
    Returns:
        List of billing plans
    """
    try:
        from shared.database.session import get_db
        from shared.models.billing_models import BillingPlan
        
        db = next(get_db())
        
        query = db.query(BillingPlan)
        if active_only:
            query = query.filter(BillingPlan.is_active == True)
        
        plans = query.order_by(BillingPlan.price_per_month).all()
        
        return [
            {
                'id': str(plan.id),
                'name': plan.name,
                'description': plan.description,
                'price_per_month': float(plan.price_per_month),
                'currency': plan.currency,
                'max_users': plan.max_users,
                'max_storage_gb': plan.max_storage_gb,
                'max_files_per_month': plan.max_files_per_month,
                'max_api_calls': plan.max_api_calls,
                'features': plan.features or {},
                'is_active': plan.is_active,
                'is_default': plan.is_default
            }
            for plan in plans
        ]
        
    except Exception as e:
        logger.error(f"Error getting billing plans: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get billing plans: {str(e)}"
        )


@router.get("/cost")
async def get_current_cost(
    tenant_id: str = Depends(verify_tenant_access),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get current cost for tenant.
    
    Args:
        tenant_id: Tenant ID
        start_date: Start date (ISO format)
        end_date: End date (ISO format)
        current_user: Current user
    
    Returns:
        Cost calculation
    """
    try:
        # Parse dates
        start = datetime.fromisoformat(start_date) if start_date else None
        end = datetime.fromisoformat(end_date) if end_date else None
        
        cost_data = cost_calculator.calculate_tenant_cost(
            tenant_id=UUID(tenant_id),
            start_date=start,
            end_date=end
        )
        
        if 'error' in cost_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=cost_data['error']
            )
        
        return cost_data
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error getting current cost: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get current cost: {str(e)}"
        )


@router.get("/forecast")
async def get_cost_forecast(
    tenant_id: str = Depends(verify_tenant_access),
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get cost forecast for tenant.
    
    Args:
        tenant_id: Tenant ID
        days: Forecast period in days
        current_user: Current user
    
    Returns:
        Cost forecast
    """
    try:
        forecast = cost_calculator.forecast_cost(
            tenant_id=UUID(tenant_id),
            forecast_days=days
        )
        
        if 'error' in forecast:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=forecast['error']
            )
        
        return forecast
        
    except Exception as e:
        logger.error(f"Error getting cost forecast: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get cost forecast: {str(e)}"
        )


@router.get("/budget")
async def get_budget_status(
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get current budget status.
    
    Args:
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        Budget status
    """
    try:
        budget_status = budget_enforcer.get_tenant_budget_status(UUID(tenant_id))
        
        return {
            'tenant_id': tenant_id,
            'budget': budget_status.get('budget', 0),
            'current_cost': budget_status.get('current_cost', 0),
            'percentage_used': budget_status.get('percentage_used', 0),
            'last_checked': budget_status.get('last_checked'),
            'is_custom': budget_status.get('is_custom', False)
        }
        
    except Exception as e:
        logger.error(f"Error getting budget status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get budget status: {str(e)}"
        )


@router.post("/budget")
async def set_custom_budget(
    budget_amount: float,
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Set custom budget for tenant.
    
    Args:
        budget_amount: Budget amount
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        Confirmation
    """
    try:
        # Check if user has permission
        # In production, you would check if user is tenant admin
        
        budget_enforcer.set_custom_budget(UUID(tenant_id), budget_amount)
        
        return {
            'message': 'Custom budget set successfully',
            'tenant_id': tenant_id,
            'budget_amount': budget_amount,
            'set_by': current_user.email or current_user.username,
            'set_at': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error setting custom budget: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set custom budget: {str(e)}"
        )


@router.get("/recommendations")
async def get_budget_recommendations(
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get budget recommendations.
    
    Args:
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        Budget recommendations
    """
    try:
        recommendations = budget_enforcer.get_budget_recommendations(UUID(tenant_id))
        
        if 'error' in recommendations:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=recommendations['error']
            )
        
        return recommendations
        
    except Exception as e:
        logger.error(f"Error getting budget recommendations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get budget recommendations: {str(e)}"
        )


@router.post("/invoices")
async def generate_invoice(
    background_tasks: BackgroundTasks,
    period_start: str,
    period_end: str,
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Generate invoice for period.
    
    Args:
        period_start: Period start date (ISO format)
        period_end: Period end date (ISO format)
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        Invoice generation result
    """
    try:
        start_date = datetime.fromisoformat(period_start)
        end_date = datetime.fromisoformat(period_end)
        
        # Calculate cost for period
        cost_data = cost_calculator.calculate_tenant_cost(
            tenant_id=UUID(tenant_id),
            start_date=start_date,
            end_date=end_date
        )
        
        if 'error' in cost_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=cost_data['error']
            )
        
        # Create invoice record
        from shared.database.session import get_db
        from shared.models.billing_models import Invoice, Subscription
        import uuid
        
        db = next(get_db())
        
        # Get subscription
        subscription = db.query(Subscription).filter(
            Subscription.tenant_id == UUID(tenant_id),
            Subscription.status == 'active'
        ).first()
        
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active subscription found"
            )
        
        # Create invoice
        invoice_number = f"INV-{datetime.now().strftime('%Y%m')}-{uuid.uuid4().hex[:8].upper()}"
        
        invoice = Invoice(
            subscription_id=subscription.id,
            invoice_number=invoice_number,
            amount=cost_data['total_cost'],
            currency=cost_data.get('currency', 'USD'),
            period_start=start_date,
            period_end=end_date,
            due_date=end_date + timedelta(days=30),
            status='draft'
        )
        
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        
        # Generate PDF invoice in background
        background_tasks.add_task(
            generate_invoice_pdf,
            invoice_id=invoice.id,
            cost_data=cost_data
        )
        
        return {
            'message': 'Invoice generated successfully',
            'invoice_id': str(invoice.id),
            'invoice_number': invoice.invoice_number,
            'amount': float(invoice.amount),
            'currency': invoice.currency,
            'status': invoice.status,
            'period': {
                'start': period_start,
                'end': period_end
            }
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error generating invoice: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate invoice: {str(e)}"
        )


def generate_invoice_pdf(invoice_id: UUID, cost_data: Dict[str, Any]):
    """Generate PDF invoice (background task)."""
    try:
        # This would generate a PDF invoice
        # For now, just log it
        logger.info(f"Generating PDF invoice for invoice {invoice_id}")
        
        # In production, you would:
        # 1. Use a template engine to generate HTML
        # 2. Convert HTML to PDF
        # 3. Store the PDF
        # 4. Send email with PDF attachment
        
    except Exception as e:
        logger.error(f"Error generating invoice PDF: {str(e)}")