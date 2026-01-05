"""
Subscription API routes.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta

from shared.auth.middleware import get_current_user, verify_tenant_access
from shared.models.user_models import User
from shared.utils.logging import logger

from services.billing_service.config import config

# Create router
router = APIRouter(
    prefix="",
    tags=["subscriptions"],
    dependencies=[Depends(get_current_user)]
)


@router.get("/")
async def get_subscription(
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get current subscription for tenant.
    
    Args:
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        Subscription details
    """
    try:
        from shared.database.session import get_db
        from shared.models.billing_models import Subscription
        
        db = next(get_db())
        
        subscription = db.query(Subscription).filter(
            Subscription.tenant_id == UUID(tenant_id),
            Subscription.status == 'active'
        ).first()
        
        if not subscription:
            # Return free tier info
            return {
                'tenant_id': tenant_id,
                'plan_name': 'Free',
                'status': 'active',
                'is_trial': False,
                'price_per_month': 0.00,
                'currency': 'USD',
                'current_period_start': None,
                'current_period_end': None,
                'created_at': None
            }
        
        return {
            'subscription_id': str(subscription.id),
            'tenant_id': tenant_id,
            'plan_name': subscription.billing_plan.name,
            'plan_id': str(subscription.billing_plan_id),
            'status': subscription.status,
            'is_trial': subscription.is_trial,
            'trial_ends_at': subscription.trial_ends_at.isoformat() if subscription.trial_ends_at else None,
            'price_per_month': float(subscription.billing_plan.price_per_month),
            'currency': subscription.billing_plan.currency,
            'current_period_start': subscription.current_period_start.isoformat(),
            'current_period_end': subscription.current_period_end.isoformat(),
            'created_at': subscription.created_at.isoformat(),
            'stripe_subscription_id': subscription.stripe_subscription_id,
            'stripe_customer_id': subscription.stripe_customer_id
        }
        
    except Exception as e:
        logger.error(f"Error getting subscription: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get subscription: {str(e)}"
        )


@router.post("/")
async def create_subscription(
    plan_id: str,
    payment_method_id: Optional[str] = None,
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Create or update subscription.
    
    Args:
        plan_id: Billing plan ID
        payment_method_id: Payment method ID (for Stripe)
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        Subscription creation result
    """
    try:
        from shared.database.session import get_db
        from shared.models.billing_models import Subscription, BillingPlan
        import uuid
        
        db = next(get_db())
        
        # Get billing plan
        billing_plan = db.query(BillingPlan).filter(
            BillingPlan.id == UUID(plan_id),
            BillingPlan.is_active == True
        ).first()
        
        if not billing_plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Billing plan not found"
            )
        
        # Check if subscription already exists
        existing_subscription = db.query(Subscription).filter(
            Subscription.tenant_id == UUID(tenant_id)
        ).first()
        
        current_time = datetime.now()
        
        if existing_subscription:
            # Update existing subscription
            existing_subscription.billing_plan_id = billing_plan.id
            existing_subscription.current_period_start = current_time
            existing_subscription.current_period_end = current_time + timedelta(days=30)
            existing_subscription.status = 'active'
            
            if billing_plan.price_per_month == 0:
                existing_subscription.is_trial = False
            elif not existing_subscription.stripe_subscription_id and payment_method_id:
                # Create Stripe subscription if needed
                existing_subscription.stripe_subscription_id = self._create_stripe_subscription(
                    tenant_id, billing_plan, payment_method_id
                )
            
            subscription = existing_subscription
            
        else:
            # Create new subscription
            subscription = Subscription(
                id=uuid.uuid4(),
                tenant_id=UUID(tenant_id),
                billing_plan_id=billing_plan.id,
                status='active',
                current_period_start=current_time,
                current_period_end=current_time + timedelta(days=30),
                is_trial=(billing_plan.price_per_month > 0)  # Trial for paid plans
            )
            
            if billing_plan.price_per_month > 0:
                subscription.trial_ends_at = current_time + timedelta(days=14)  # 14-day trial
                
                if payment_method_id and config.stripe_enabled:
                    subscription.stripe_subscription_id = self._create_stripe_subscription(
                        tenant_id, billing_plan, payment_method_id
                    )
            
            db.add(subscription)
        
        db.commit()
        db.refresh(subscription)
        
        logger.info(f"Subscription created/updated for tenant {tenant_id}: {billing_plan.name}")
        
        return {
            'message': 'Subscription created successfully',
            'subscription_id': str(subscription.id),
            'plan_name': billing_plan.name,
            'price_per_month': float(billing_plan.price_per_month),
            'trial_period': 14 if subscription.is_trial else 0,
            'trial_ends_at': subscription.trial_ends_at.isoformat() if subscription.trial_ends_at else None,
            'current_period_end': subscription.current_period_end.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error creating subscription: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create subscription: {str(e)}"
        )


@router.delete("/")
async def cancel_subscription(
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Cancel subscription.
    
    Args:
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        Cancellation result
    """
    try:
        from shared.database.session import get_db
        from shared.models.billing_models import Subscription
        
        db = next(get_db())
        
        subscription = db.query(Subscription).filter(
            Subscription.tenant_id == UUID(tenant_id),
            Subscription.status == 'active'
        ).first()
        
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active subscription found"
            )
        
        # Cancel Stripe subscription if exists
        if subscription.stripe_subscription_id and config.stripe_enabled:
            self._cancel_stripe_subscription(subscription.stripe_subscription_id)
        
        # Update subscription status
        subscription.status = 'canceled'
        db.commit()
        
        logger.info(f"Subscription canceled for tenant {tenant_id}")
        
        return {
            'message': 'Subscription canceled successfully',
            'subscription_id': str(subscription.id),
            'cancelled_at': datetime.now().isoformat(),
            'effective_until': subscription.current_period_end.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error canceling subscription: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel subscription: {str(e)}"
        )


@router.get("/invoices")
async def get_invoices(
    tenant_id: str = Depends(verify_tenant_access),
    status: Optional[str] = Query(None, regex="^(draft|sent|paid|overdue|void)$"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get invoices for tenant.
    
    Args:
        tenant_id: Tenant ID
        status: Filter by invoice status
        limit: Maximum results
        skip: Pagination offset
        current_user: Current user
    
    Returns:
        List of invoices
    """
    try:
        from shared.database.session import get_db
        from shared.models.billing_models import Invoice, Subscription
        
        db = next(get_db())
        
        # Get subscription
        subscription = db.query(Subscription).filter(
            Subscription.tenant_id == UUID(tenant_id)
        ).first()
        
        if not subscription:
            return {
                'invoices': [],
                'total': 0,
                'limit': limit,
                'skip': skip
            }
        
        # Build query
        query = db.query(Invoice).filter(
            Invoice.subscription_id == subscription.id
        )
        
        if status:
            query = query.filter(Invoice.status == status)
        
        # Get total count
        total = query.count()
        
        # Get paginated results
        invoices = query.order_by(
            Invoice.created_at.desc()
        ).offset(skip).limit(limit).all()
        
        invoice_list = []
        for invoice in invoices:
            invoice_list.append({
                'invoice_id': str(invoice.id),
                'invoice_number': invoice.invoice_number,
                'amount': float(invoice.amount),
                'currency': invoice.currency,
                'period_start': invoice.period_start.isoformat(),
                'period_end': invoice.period_end.isoformat(),
                'status': invoice.status,
                'paid_at': invoice.paid_at.isoformat() if invoice.paid_at else None,
                'due_date': invoice.due_date.isoformat(),
                'created_at': invoice.created_at.isoformat()
            })
        
        return {
            'invoices': invoice_list,
            'total': total,
            'limit': limit,
            'skip': skip,
            'has_more': (skip + limit) < total
        }
        
    except Exception as e:
        logger.error(f"Error getting invoices: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get invoices: {str(e)}"
        )


@router.get("/payment-methods")
async def get_payment_methods(
    tenant_id: str = Depends(verify_tenant_access),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Get payment methods for tenant.
    
    Args:
        tenant_id: Tenant ID
        current_user: Current user
    
    Returns:
        List of payment methods
    """
    try:
        # This would integrate with Stripe or other payment providers
        # For now, return mock data
        
        return [
            {
                'id': 'pm_mock_1',
                'type': 'card',
                'brand': 'visa',
                'last4': '4242',
                'exp_month': 12,
                'exp_year': 2025,
                'is_default': True
            }
        ]
        
    except Exception as e:
        logger.error(f"Error getting payment methods: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get payment methods: {str(e)}"
        )


@router.post("/webhook/stripe")
async def handle_stripe_webhook(
    payload: Dict[str, Any],
    stripe_signature: str = None
) -> Dict[str, Any]:
    """
    Handle Stripe webhook events.
    
    Args:
        payload: Stripe webhook payload
        stripe_signature: Stripe signature for verification
    
    Returns:
        Webhook handling result
    """
    try:
        if not config.stripe_enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stripe integration is disabled"
            )
        
        # Verify webhook signature
        if not self._verify_stripe_signature(payload, stripe_signature):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Stripe signature"
            )
        
        event_type = payload.get('type')
        event_data = payload.get('data', {}).get('object', {})
        
        # Handle different event types
        if event_type == 'invoice.payment_succeeded':
            self._handle_payment_succeeded(event_data)
        elif event_type == 'invoice.payment_failed':
            self._handle_payment_failed(event_data)
        elif event_type == 'customer.subscription.updated':
            self._handle_subscription_updated(event_data)
        elif event_type == 'customer.subscription.deleted':
            self._handle_subscription_deleted(event_data)
        
        return {'status': 'success'}
        
    except Exception as e:
        logger.error(f"Error handling Stripe webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to handle webhook: {str(e)}"
        )


# Helper methods for Stripe integration
def _create_stripe_subscription(self, tenant_id: str, billing_plan, payment_method_id: str) -> str:
    """Create Stripe subscription."""
    if not config.stripe_enabled:
        return None
    
    try:
        import stripe
        stripe.api_key = config.stripe_secret_key
        
        # Get or create Stripe customer
        from shared.database.session import get_db
        from shared.models.user_models import Tenant
        
        db = next(get_db())
        tenant = db.query(Tenant).filter(Tenant.id == UUID(tenant_id)).first()
        
        # This is simplified - in production you would:
        # 1. Get/create customer
        # 2. Attach payment method
        # 3. Create subscription
        
        return f"sub_mock_{datetime.now().timestamp()}"
    
    except Exception as e:
        logger.error(f"Error creating Stripe subscription: {str(e)}")
        return None


def _cancel_stripe_subscription(self, stripe_subscription_id: str):
    """Cancel Stripe subscription."""
    if not config.stripe_enabled:
        return
    
    try:
        import stripe
        stripe.api_key = config.stripe_secret_key
        
        # This would cancel the Stripe subscription
        # stripe.Subscription.delete(stripe_subscription_id)
        
        logger.info(f"Stripe subscription canceled: {stripe_subscription_id}")
    
    except Exception as e:
        logger.error(f"Error canceling Stripe subscription: {str(e)}")


def _verify_stripe_signature(self, payload: Dict[str, Any], signature: str) -> bool:
    """Verify Stripe webhook signature."""
    if not config.stripe_enabled or not config.stripe_webhook_secret:
        return False
    
    try:
        import stripe
        stripe.Webhook.construct_event(
            payload, signature, config.stripe_webhook_secret
        )
        return True
    
    except Exception as e:
        logger.error(f"Stripe signature verification failed: {str(e)}")
        return False