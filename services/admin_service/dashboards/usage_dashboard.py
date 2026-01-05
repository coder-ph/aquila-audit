"""
Usage dashboard for admin service.
"""
from typing import Dict, List, Any, Optional, Tuple
from uuid import UUID
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc

from shared.database.session import get_db
from shared.models.user_models import Tenant
from shared.models.billing_models import UsageRecord, Subscription
from shared.utils.logging import logger


class UsageDashboard:
    """Provides usage data for admin dashboard."""
    
    def __init__(self):
        pass
    
    def get_overview_stats(self) -> Dict[str, Any]:
        """Get overview statistics."""
        db: Session = next(get_db())
        
        try:
            # Count tenants
            total_tenants = db.query(func.count(Tenant.id)).scalar() or 0
            active_tenants = db.query(func.count(Tenant.id)).filter(
                Tenant.is_active == True
            ).scalar() or 0
            
            # Count subscriptions
            total_subscriptions = db.query(func.count(Subscription.id)).scalar() or 0
            active_subscriptions = db.query(func.count(Subscription.id)).filter(
                Subscription.status == 'active'
            ).scalar() or 0
            
            # Get revenue (simplified)
            revenue = self._calculate_revenue(db)
            
            # Get usage trends
            usage_trend = self._get_usage_trend(db)
            
            return {
                'tenants': {
                    'total': total_tenants,
                    'active': active_tenants,
                    'inactive': total_tenants - active_tenants
                },
                'subscriptions': {
                    'total': total_subscriptions,
                    'active': active_subscriptions,
                    'trial': db.query(func.count(Subscription.id)).filter(
                        Subscription.is_trial == True
                    ).scalar() or 0
                },
                'revenue': revenue,
                'usage_trend': usage_trend,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting overview stats: {str(e)}")
            return {
                'error': str(e),
                'tenants': {'total': 0, 'active': 0, 'inactive': 0},
                'subscriptions': {'total': 0, 'active': 0, 'trial': 0},
                'revenue': {'monthly': 0, 'annual': 0},
                'timestamp': datetime.now().isoformat()
            }
        finally:
            db.close()
    
    def _calculate_revenue(self, db: Session) -> Dict[str, float]:
        """Calculate revenue statistics."""
        try:
            # Sum of all active subscription prices
            from shared.models.billing_models import BillingPlan
            
            monthly_revenue = db.query(
                func.sum(BillingPlan.price_per_month)
            ).join(
                Subscription, Subscription.billing_plan_id == BillingPlan.id
            ).filter(
                Subscription.status == 'active',
                Subscription.is_trial == False
            ).scalar() or 0
            
            return {
                'monthly': float(monthly_revenue),
                'annual': float(monthly_revenue * 12),
                'currency': 'USD'
            }
            
        except Exception as e:
            logger.error(f"Error calculating revenue: {str(e)}")
            return {'monthly': 0, 'annual': 0, 'currency': 'USD'}
    
    def _get_usage_trend(self, db: Session) -> Dict[str, Any]:
        """Get usage trend over time."""
        try:
            # Get last 30 days of usage
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            # Query daily usage
            daily_usage = db.query(
                func.date_trunc('day', UsageRecord.recorded_at).label('date'),
                UsageRecord.metric_name,
                func.sum(UsageRecord.metric_value).label('total')
            ).filter(
                UsageRecord.recorded_at >= start_date,
                UsageRecord.recorded_at <= end_date,
                UsageRecord.metric_name.in_(['file_uploads', 'api_calls', 'storage_bytes'])
            ).group_by(
                func.date_trunc('day', UsageRecord.recorded_at),
                UsageRecord.metric_name
            ).order_by(
                func.date_trunc('day', UsageRecord.recorded_at)
            ).all()
            
            # Organize data
            dates = []
            file_uploads = []
            api_calls = []
            storage_gb = []
            
            current_date = start_date
            while current_date <= end_date:
                date_str = current_date.strftime('%Y-%m-%d')
                dates.append(date_str)
                
                # Find data for this date
                date_data = [d for d in daily_usage if d.date.date() == current_date.date()]
                
                files = next((d.total for d in date_data if d.metric_name == 'file_uploads'), 0)
                api = next((d.total for d in date_data if d.metric_name == 'api_calls'), 0)
                storage = next((d.total for d in date_data if d.metric_name == 'storage_bytes'), 0) / (1024 ** 3)
                
                file_uploads.append(files)
                api_calls.append(api)
                storage_gb.append(round(storage, 2))
                
                current_date += timedelta(days=1)
            
            # Calculate trends
            def calculate_trend(data):
                if len(data) < 2:
                    return 0
                first_half = sum(data[:len(data)//2])
                second_half = sum(data[len(data)//2:])
                if first_half == 0:
                    return 100 if second_half > 0 else 0
                return ((second_half - first_half) / first_half) * 100
            
            return {
                'dates': dates,
                'metrics': {
                    'file_uploads': {
                        'data': file_uploads,
                        'total': sum(file_uploads),
                        'trend': calculate_trend(file_uploads)
                    },
                    'api_calls': {
                        'data': api_calls,
                        'total': sum(api_calls),
                        'trend': calculate_trend(api_calls)
                    },
                    'storage_gb': {
                        'data': storage_gb,
                        'total': sum(storage_gb),
                        'trend': calculate_trend(storage_gb)
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting usage trend: {str(e)}")
            return {
                'dates': [],
                'metrics': {
                    'file_uploads': {'data': [], 'total': 0, 'trend': 0},
                    'api_calls': {'data': [], 'total': 0, 'trend': 0},
                    'storage_gb': {'data': [], 'total': 0, 'trend': 0}
                }
            }
    
    def get_tenant_usage_ranking(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get tenants ranked by usage."""
        db: Session = next(get_db())
        
        try:
            # Get usage for last 30 days
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            # Query tenant usage
            tenant_usage = db.query(
                UsageRecord.tenant_id,
                func.sum(
                    func.case(
                        (UsageRecord.metric_name == 'file_uploads', UsageRecord.metric_value),
                        else_=0
                    )
                ).label('file_uploads'),
                func.sum(
                    func.case(
                        (UsageRecord.metric_name == 'api_calls', UsageRecord.metric_value),
                        else_=0
                    )
                ).label('api_calls'),
                func.sum(
                    func.case(
                        (UsageRecord.metric_name == 'storage_bytes', UsageRecord.metric_value),
                        else_=0
                    )
                ).label('storage_bytes')
            ).filter(
                UsageRecord.recorded_at >= start_date,
                UsageRecord.recorded_at <= end_date
            ).group_by(UsageRecord.tenant_id).all()
            
            # Get tenant details and format results
            ranking = []
            for tenant_id, files, api, storage in tenant_usage:
                tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
                if tenant:
                    ranking.append({
                        'tenant_id': str(tenant_id),
                        'tenant_name': tenant.name,
                        'tenant_slug': tenant.slug,
                        'file_uploads': files or 0,
                        'api_calls': api or 0,
                        'storage_gb': (storage or 0) / (1024 ** 3),
                        'is_active': tenant.is_active
                    })
            
            # Sort by total usage score (simple weighted sum)
            for tenant in ranking:
                tenant['usage_score'] = (
                    tenant['file_uploads'] * 1 +
                    tenant['api_calls'] * 0.1 +
                    tenant['storage_gb'] * 10
                )
            
            ranking.sort(key=lambda x: x['usage_score'], reverse=True)
            
            return ranking[:limit]
            
        except Exception as e:
            logger.error(f"Error getting tenant usage ranking: {str(e)}")
            return []
        finally:
            db.close()
    
    def get_plan_distribution(self) -> Dict[str, Any]:
        """Get distribution of billing plans."""
        db: Session = next(get_db())
        
        try:
            from shared.models.billing_models import BillingPlan
            
            # Get plan counts
            plan_counts = db.query(
                BillingPlan.name,
                func.count(Subscription.id).label('count')
            ).join(
                Subscription, Subscription.billing_plan_id == BillingPlan.id
            ).filter(
                Subscription.status == 'active'
            ).group_by(BillingPlan.name).all()
            
            # Format results
            distribution = {
                'plans': [
                    {'name': name, 'count': count}
                    for name, count in plan_counts
                ],
                'total': sum(count for _, count in plan_counts)
            }
            
            return distribution
            
        except Exception as e:
            logger.error(f"Error getting plan distribution: {str(e)}")
            return {'plans': [], 'total': 0}
        finally:
            db.close()
    
    def get_active_alerts_summary(self) -> Dict[str, Any]:
        """Get summary of active alerts."""
        try:
            # This would integrate with the alert manager
            # For now, return mock data
            
            return {
                'critical': 2,
                'warning': 5,
                'total': 7,
                'latest_alerts': [
                    {
                        'id': 'alert_1',
                        'tenant': 'example-tenant',
                        'type': 'budget_critical',
                        'message': 'Budget exceeded 95%',
                        'created_at': datetime.now().isoformat()
                    },
                    {
                        'id': 'alert_2',
                        'tenant': 'another-tenant',
                        'type': 'usage_limit',
                        'message': 'Storage usage at 88% of limit',
                        'created_at': (datetime.now() - timedelta(hours=2)).isoformat()
                    }
                ]
            }
            
        except Exception as e:
            logger.error(f"Error getting alerts summary: {str(e)}")
            return {'critical': 0, 'warning': 0, 'total': 0, 'latest_alerts': []}


# Global usage dashboard instance
usage_dashboard = UsageDashboard()