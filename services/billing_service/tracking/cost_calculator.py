"""
Cost calculator for usage-based billing.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from uuid import UUID
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from shared.database.session import get_db
from shared.models.billing_models import BillingPlan, Subscription, UsageRecord
from shared.utils.logging import logger
from services.billing_service.config import config


class CostCalculator:
    """Calculates costs based on usage and billing plans."""
    
    def __init__(self):
        pass
    
    def calculate_tenant_cost(
        self,
        tenant_id: UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculate costs for a tenant.
        
        Args:
            tenant_id: Tenant UUID
            start_date: Start date for calculation
            end_date: End date for calculation
        
        Returns:
            Cost calculation details
        """
        db: Session = next(get_db())
        
        try:
            # Default to current month
            if not start_date:
                start_date = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if not end_date:
                end_date = datetime.now()
            
            # Get tenant's subscription
            subscription = db.query(Subscription).filter(
                Subscription.tenant_id == tenant_id,
                Subscription.status == 'active'
            ).first()
            
            if not subscription:
                return self._calculate_free_tier_cost(db, tenant_id, start_date, end_date)
            
            # Get usage for period
            usage = self._get_usage_for_period(db, tenant_id, start_date, end_date)
            
            # Calculate costs based on plan
            if subscription.billing_plan.price_per_month == 0:
                # Free tier
                return self._calculate_free_tier_cost(db, tenant_id, start_date, end_date, usage)
            else:
                # Paid tier
                return self._calculate_paid_tier_cost(db, tenant_id, subscription, start_date, end_date, usage)
        
        except Exception as e:
            logger.error(f"Error calculating tenant cost: {str(e)}")
            return {
                'tenant_id': str(tenant_id),
                'error': str(e)
            }
        finally:
            db.close()
    
    def _get_usage_for_period(
        self,
        db: Session,
        tenant_id: UUID,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Get usage metrics for a period."""
        # Get aggregated usage records
        usage_records = db.query(
            UsageRecord.metric_name,
            func.sum(UsageRecord.metric_value).label('total')
        ).filter(
            UsageRecord.tenant_id == tenant_id,
            UsageRecord.recorded_at >= start_date,
            UsageRecord.recorded_at <= end_date
        ).group_by(UsageRecord.metric_name).all()
        
        usage = {}
        for record in usage_records:
            usage[record.metric_name] = record.total
        
        return usage
    
    def _calculate_free_tier_cost(
        self,
        db: Session,
        tenant_id: UUID,
        start_date: datetime,
        end_date: datetime,
        usage: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Calculate costs for free tier."""
        if usage is None:
            usage = self._get_usage_for_period(db, tenant_id, start_date, end_date)
        
        # Get free plan limits
        free_plan = db.query(BillingPlan).filter(
            BillingPlan.is_default == True,
            BillingPlan.price_per_month == 0
        ).first()
        
        if not free_plan:
            free_plan = BillingPlan(
                max_users=1,
                max_storage_gb=1,
                max_files_per_month=100,
                max_api_calls=1000
            )
        
        # Calculate usage vs limits
        storage_gb = usage.get('storage_gb', 0) or (usage.get('storage_bytes', 0) / (1024 ** 3))
        file_uploads = usage.get('file_uploads', 0)
        
        return {
            'tenant_id': str(tenant_id),
            'plan_name': 'Free',
            'plan_price': 0.00,
            'currency': 'USD',
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
                'days': (end_date - start_date).days
            },
            'usage': usage,
            'limits': {
                'max_users': free_plan.max_users,
                'max_storage_gb': free_plan.max_storage_gb,
                'max_files_per_month': free_plan.max_files_per_month,
                'max_api_calls': free_plan.max_api_calls
            },
            'usage_percentages': {
                'storage': min(100, (storage_gb / free_plan.max_storage_gb) * 100) if free_plan.max_storage_gb else 0,
                'files': min(100, (file_uploads / free_plan.max_files_per_month) * 100) if free_plan.max_files_per_month else 0,
                'api_calls': min(100, (usage.get('api_calls', 0) / free_plan.max_api_calls) * 100) if free_plan.max_api_calls else 0
            },
            'total_cost': 0.00,
            'overage_cost': 0.00,
            'has_overages': False,
            'within_limits': True
        }
    
    def _calculate_paid_tier_cost(
        self,
        db: Session,
        tenant_id: UUID,
        subscription: Subscription,
        start_date: datetime,
        end_date: datetime,
        usage: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate costs for paid tier."""
        plan = subscription.billing_plan
        
        # Calculate base cost
        days_in_period = (end_date - start_date).days
        monthly_cost = float(plan.price_per_month)
        daily_cost = monthly_cost / 30  # Simple daily proration
        base_cost = daily_cost * days_in_period
        
        # Calculate overage costs
        overage_costs = {}
        total_overage_cost = 0.00
        
        # Storage overage
        storage_gb = usage.get('storage_gb', 0) or (usage.get('storage_bytes', 0) / (1024 ** 3))
        if plan.max_storage_gb and storage_gb > plan.max_storage_gb:
            overage_gb = storage_gb - plan.max_storage_gb
            storage_overage = overage_gb * config.cost_per_storage_gb * (days_in_period / 30)
            overage_costs['storage'] = {
                'overage_gb': overage_gb,
                'rate_per_gb': config.cost_per_storage_gb,
                'cost': storage_overage
            }
            total_overage_cost += storage_overage
        
        # File upload overage
        file_uploads = usage.get('file_uploads', 0)
        if plan.max_files_per_month and file_uploads > plan.max_files_per_month:
            overage_files = file_uploads - plan.max_files_per_month
            file_overage = overage_files * config.cost_per_file_upload
            overage_costs['file_uploads'] = {
                'overage_files': overage_files,
                'rate_per_file': config.cost_per_file_upload,
                'cost': file_overage
            }
            total_overage_cost += file_overage
        
        # API call overage
        api_calls = usage.get('api_calls', 0)
        if plan.max_api_calls and api_calls > plan.max_api_calls:
            overage_calls = api_calls - plan.max_api_calls
            api_overage = overage_calls * config.cost_per_api_call
            overage_costs['api_calls'] = {
                'overage_calls': overage_calls,
                'rate_per_call': config.cost_per_api_call,
                'cost': api_overage
            }
            total_overage_cost += api_overage
        
        # AI token overage
        ai_tokens = usage.get('ai_tokens_used', 0)
        # For now, all AI usage is considered overage for simplicity
        if ai_tokens > 0:
            ai_cost = ai_tokens * config.cost_per_ai_token
            overage_costs['ai_tokens'] = {
                'tokens_used': ai_tokens,
                'rate_per_token': config.cost_per_ai_token,
                'cost': ai_cost
            }
            total_overage_cost += ai_cost
        
        total_cost = base_cost + total_overage_cost
        
        # Calculate usage percentages
        usage_percentages = {}
        if plan.max_storage_gb:
            usage_percentages['storage'] = min(100, (storage_gb / plan.max_storage_gb) * 100)
        if plan.max_files_per_month:
            usage_percentages['files'] = min(100, (file_uploads / plan.max_files_per_month) * 100)
        if plan.max_api_calls:
            usage_percentages['api_calls'] = min(100, (api_calls / plan.max_api_calls) * 100)
        
        return {
            'tenant_id': str(tenant_id),
            'subscription_id': str(subscription.id),
            'plan_name': plan.name,
            'plan_price': float(plan.price_per_month),
            'currency': plan.currency,
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
                'days': days_in_period
            },
            'usage': usage,
            'limits': {
                'max_users': plan.max_users,
                'max_storage_gb': plan.max_storage_gb,
                'max_files_per_month': plan.max_files_per_month,
                'max_api_calls': plan.max_api_calls
            },
            'usage_percentages': usage_percentages,
            'cost_breakdown': {
                'base_cost': base_cost,
                'overage_costs': overage_costs,
                'total_overage_cost': total_overage_cost
            },
            'total_cost': total_cost,
            'has_overages': len(overage_costs) > 0,
            'within_limits': total_overage_cost == 0
        }
    
    def forecast_cost(
        self,
        tenant_id: UUID,
        forecast_days: int = 30
    ) -> Dict[str, Any]:
        """Forecast future costs based on current usage patterns."""
        db: Session = next(get_db())
        
        try:
            # Get current usage for last 30 days
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            current_cost = self.calculate_tenant_cost(tenant_id, start_date, end_date)
            
            if 'error' in current_cost:
                return current_cost
            
            # Calculate daily averages
            usage = current_cost.get('usage', {})
            days_in_period = 30
            
            daily_averages = {}
            for metric, value in usage.items():
                daily_averages[metric] = value / days_in_period
            
            # Forecast future usage
            forecasted_usage = {}
            for metric, daily_avg in daily_averages.items():
                forecasted_usage[metric] = daily_avg * forecast_days
            
            # Get subscription for pricing
            subscription = db.query(Subscription).filter(
                Subscription.tenant_id == tenant_id,
                Subscription.status == 'active'
            ).first()
            
            if subscription:
                plan = subscription.billing_plan
                plan_name = plan.name
                plan_price = float(plan.price_per_month)
            else:
                plan_name = 'Free'
                plan_price = 0.00
            
            # Simple forecast calculation
            # In production, this would be more sophisticated
            forecasted_cost = {
                'tenant_id': str(tenant_id),
                'plan_name': plan_name,
                'forecast_period_days': forecast_days,
                'forecast_start': end_date.isoformat(),
                'forecast_end': (end_date + timedelta(days=forecast_days)).isoformat(),
                'daily_averages': daily_averages,
                'forecasted_usage': forecasted_usage,
                'estimated_monthly_cost': plan_price,
                'estimated_overage_cost': 0.00,  # Simplified
                'estimated_total_cost': plan_price,
                'confidence_score': 0.7  # Medium confidence
            }
            
            return forecasted_cost
            
        except Exception as e:
            logger.error(f"Error forecasting cost: {str(e)}")
            return {
                'tenant_id': str(tenant_id),
                'error': str(e)
            }
        finally:
            db.close()


# Global cost calculator instance
cost_calculator = CostCalculator()