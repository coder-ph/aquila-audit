"""
Budget enforcement and spending limits.
"""
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from shared.database.session import get_db
from shared.models.billing_models import Subscription
from shared.utils.logging import logger
from services.billing_service.config import config
from services.billing_service.alerts.alert_manager import alert_manager


class BudgetEnforcer:
    """Enforces spending limits and budgets."""
    
    def __init__(self):
        self.running = False
        self.monitoring_thread = None
        self.tenant_budgets = {}  # In-memory cache of tenant budgets
    
    def start_monitoring(self):
        """Start budget monitoring."""
        if self.running:
            logger.warning("Budget monitoring already running")
            return
        
        self.running = True
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True
        )
        self.monitoring_thread.start()
        logger.info("Budget monitoring started")
    
    def stop_monitoring(self):
        """Stop budget monitoring."""
        self.running = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        logger.info("Budget monitoring stopped")
    
    def _monitoring_loop(self):
        """Background monitoring loop."""
        while self.running:
            try:
                self.check_all_tenant_budgets()
                time.sleep(300)  # Check every 5 minutes
            except Exception as e:
                logger.error(f"Error in budget monitoring loop: {str(e)}")
                time.sleep(60)
    
    def check_all_tenant_budgets(self):
        """Check budgets for all tenants."""
        db: Session = next(get_db())
        
        try:
            # Get all active subscriptions
            subscriptions = db.query(Subscription).filter(
                Subscription.status == 'active'
            ).all()
            
            for subscription in subscriptions:
                self.check_tenant_budget(subscription.tenant_id)
            
            logger.debug(f"Checked budgets for {len(subscriptions)} tenants")
            
        except Exception as e:
            logger.error(f"Error checking budgets: {str(e)}")
        finally:
            db.close()
    
    def check_tenant_budget(self, tenant_id: UUID):
        """Check budget for a specific tenant."""
        try:
            from services.billing_service.tracking.cost_calculator import cost_calculator
            
            # Calculate current month cost
            month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            cost_data = cost_calculator.calculate_tenant_cost(tenant_id, month_start, datetime.now())
            
            if 'error' in cost_data:
                logger.error(f"Error calculating cost for tenant {tenant_id}: {cost_data['error']}")
                return
            
            # Check subscription for budget
            db: Session = next(get_db())
            subscription = db.query(Subscription).filter(
                Subscription.tenant_id == tenant_id,
                Subscription.status == 'active'
            ).first()
            
            if not subscription:
                return
            
            # Get plan price as budget (simplified)
            plan_price = float(subscription.billing_plan.price_per_month)
            current_cost = cost_data.get('total_cost', 0)
            
            # Calculate percentage used
            if plan_price > 0:
                percentage_used = (current_cost / plan_price) * 100
            else:
                # For free tier, track usage against limits
                percentage_used = self._calculate_free_tier_usage(cost_data)
            
            # Update cache
            self.tenant_budgets[str(tenant_id)] = {
                'budget': plan_price,
                'current_cost': current_cost,
                'percentage_used': percentage_used,
                'last_checked': datetime.now().isoformat()
            }
            
            # Check thresholds and trigger alerts
            self._check_budget_thresholds(tenant_id, percentage_used, current_cost, plan_price)
            
        except Exception as e:
            logger.error(f"Error checking tenant budget: {str(e)}")
    
    def _calculate_free_tier_usage(self, cost_data: Dict[str, Any]) -> float:
        """Calculate usage percentage for free tier."""
        usage_percentages = cost_data.get('usage_percentages', {})
        
        if not usage_percentages:
            return 0
        
        # Use the highest usage percentage
        max_percentage = 0
        for metric, percentage in usage_percentages.items():
            if percentage > max_percentage:
                max_percentage = percentage
        
        return max_percentage
    
    def _check_budget_thresholds(
        self,
        tenant_id: UUID,
        percentage_used: float,
        current_cost: float,
        budget: float
    ):
        """Check budget thresholds and trigger alerts."""
        # Warning threshold
        if percentage_used >= config.budget_warning_threshold * 100:
            alert_manager.trigger_budget_alert(
                tenant_id=tenant_id,
                alert_type='budget_warning',
                severity='warning',
                message=f"Budget warning: {percentage_used:.1f}% of budget used",
                details={
                    'percentage_used': percentage_used,
                    'current_cost': current_cost,
                    'budget': budget,
                    'threshold': config.budget_warning_threshold
                }
            )
        
        # Critical threshold
        if percentage_used >= config.budget_critical_threshold * 100:
            alert_manager.trigger_budget_alert(
                tenant_id=tenant_id,
                alert_type='budget_critical',
                severity='critical',
                message=f"Budget critical: {percentage_used:.1f}% of budget used",
                details={
                    'percentage_used': percentage_used,
                    'current_cost': current_cost,
                    'budget': budget,
                    'threshold': config.budget_critical_threshold
                }
            )
            
            # Take action for critical overage
            self._enforce_budget_limit(tenant_id)
    
    def _enforce_budget_limit(self, tenant_id: UUID):
        """Enforce budget limits for critical overage."""
        logger.warning(f"Enforcing budget limit for tenant {tenant_id}")
        
        # Actions to take:
        # 1. Send critical alert
        # 2. Potentially throttle services
        # 3. Notify administrators
        
        # For now, just log the action
        # In production, you might:
        # - Disable certain features
        # - Queue processing instead of immediate
        # - Require payment before continuing
        
        pass
    
    def get_tenant_budget_status(self, tenant_id: UUID) -> Dict[str, Any]:
        """Get current budget status for a tenant."""
        # Try cache first
        if str(tenant_id) in self.tenant_budgets:
            cached = self.tenant_budgets[str(tenant_id)]
            if datetime.fromisoformat(cached['last_checked']) > datetime.now() - timedelta(minutes=10):
                return cached
        
        # Calculate fresh
        self.check_tenant_budget(tenant_id)
        
        return self.tenant_budgets.get(str(tenant_id), {
            'budget': 0,
            'current_cost': 0,
            'percentage_used': 0,
            'last_checked': None
        })
    
    def set_custom_budget(self, tenant_id: UUID, budget_amount: float):
        """Set a custom budget for a tenant."""
        self.tenant_budgets[str(tenant_id)] = {
            'budget': budget_amount,
            'current_cost': 0,
            'percentage_used': 0,
            'last_checked': datetime.now().isoformat(),
            'is_custom': True
        }
        
        logger.info(f"Set custom budget for tenant {tenant_id}: ${budget_amount}")
    
    def get_budget_recommendations(self, tenant_id: UUID) -> Dict[str, Any]:
        """Get budget recommendations based on usage patterns."""
        try:
            from services.billing_service.tracking.cost_calculator import cost_calculator
            
            # Get cost forecast
            forecast = cost_calculator.forecast_cost(tenant_id, 30)
            
            if 'error' in forecast:
                return {
                    'tenant_id': str(tenant_id),
                    'error': forecast['error']
                }
            
            # Get current budget status
            budget_status = self.get_tenant_budget_status(tenant_id)
            
            # Calculate recommendations
            estimated_monthly = forecast.get('estimated_total_cost', 0)
            current_budget = budget_status.get('budget', 0)
            
            recommendations = []
            
            if estimated_monthly > current_budget * 1.2:  # 20% over budget
                recommendations.append({
                    'type': 'increase_budget',
                    'priority': 'high',
                    'message': f'Projected costs (${estimated_monthly:.2f}) exceed current budget by 20%',
                    'suggested_budget': estimated_monthly * 1.1,  # 10% buffer
                    'reason': 'usage_growth'
                })
            
            elif estimated_monthly < current_budget * 0.5:  # Using less than 50% of budget
                recommendations.append({
                    'type': 'decrease_budget',
                    'priority': 'low',
                    'message': f'Projected costs (${estimated_monthly:.2f}) are less than 50% of budget',
                    'suggested_budget': estimated_monthly * 1.5,  # 50% buffer
                    'reason': 'under_utilization'
                })
            
            # Check for cost optimization opportunities
            from services.billing_service.tracking.usage_tracker import usage_tracker
            usage_summary = usage_tracker.get_usage_summary(tenant_id)
            
            storage_gb = usage_summary.get('storage_gb', 0)
            if storage_gb > 50:  # More than 50GB storage
                recommendations.append({
                    'type': 'optimize_storage',
                    'priority': 'medium',
                    'message': f'Large storage usage ({storage_gb:.1f} GB). Consider cleaning up old files.',
                    'estimated_savings': storage_gb * 0.5 * config.cost_per_storage_gb,  # 50% reduction potential
                    'actions': ['Archive old reports', 'Delete unused files']
                })
            
            return {
                'tenant_id': str(tenant_id),
                'current_budget': current_budget,
                'estimated_monthly_cost': estimated_monthly,
                'budget_utilization': (estimated_monthly / current_budget * 100) if current_budget > 0 else 0,
                'recommendations': recommendations,
                'generated_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting budget recommendations: {str(e)}")
            return {
                'tenant_id': str(tenant_id),
                'error': str(e)
            }


# Global budget enforcer instance
budget_enforcer = BudgetEnforcer()