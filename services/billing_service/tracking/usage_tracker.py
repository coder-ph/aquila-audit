"""
Usage tracker for monitoring tenant usage metrics.
"""
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from uuid import UUID
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from shared.database.session import get_db
from shared.models.billing_models import UsageRecord
from shared.models.user_models import Tenant
from shared.models.file_models import UploadedFile
from shared.models.report_models import Report
from shared.utils.logging import logger
from services.billing_service.config import config


class UsageTracker:
    """Tracks usage metrics for tenants."""
    
    def __init__(self):
        self.running = False
        self.aggregation_thread = None
        self.usage_cache = {}  # In-memory cache for quick access
        
    def start_background_aggregation(self):
        """Start background usage aggregation."""
        if self.running:
            logger.warning("Usage aggregation already running")
            return
        
        self.running = True
        self.aggregation_thread = threading.Thread(
            target=self._aggregation_loop,
            daemon=True
        )
        self.aggregation_thread.start()
        logger.info("Usage aggregation started")
    
    def stop_background_aggregation(self):
        """Stop background usage aggregation."""
        self.running = False
        if self.aggregation_thread:
            self.aggregation_thread.join(timeout=5)
        logger.info("Usage aggregation stopped")
    
    def _aggregation_loop(self):
        """Background loop for aggregating usage data."""
        while self.running:
            try:
                self.aggregate_usage_data()
                time.sleep(config.usage_aggregation_interval)
            except Exception as e:
                logger.error(f"Error in usage aggregation loop: {str(e)}")
                time.sleep(60)  # Wait before retrying
    
    def aggregate_usage_data(self):
        """Aggregate usage data from various sources."""
        db: Session = next(get_db())
        
        try:
            # Get all active tenants
            tenants = db.query(Tenant).filter(Tenant.is_active == True).all()
            
            for tenant in tenants:
                # Calculate various usage metrics
                metrics = self._calculate_tenant_metrics(db, tenant.id)
                
                # Store aggregated metrics
                self._store_usage_metrics(db, tenant.id, metrics)
                
                # Update cache
                self.usage_cache[str(tenant.id)] = {
                    'metrics': metrics,
                    'last_updated': datetime.now().isoformat()
                }
            
            logger.info(f"Aggregated usage data for {len(tenants)} tenants")
            
        except Exception as e:
            logger.error(f"Error aggregating usage data: {str(e)}")
        finally:
            db.close()
    
    def _calculate_tenant_metrics(self, db: Session, tenant_id: UUID) -> Dict[str, Any]:
        """Calculate usage metrics for a tenant."""
        metrics = {
            'file_uploads': self._count_file_uploads(db, tenant_id),
            'storage_bytes': self._calculate_storage_usage(db, tenant_id),
            'reports_generated': self._count_reports_generated(db, tenant_id),
            'api_calls': self._count_api_calls(db, tenant_id),
            'ai_tokens_used': self._estimate_ai_usage(db, tenant_id),
            'active_users': self._count_active_users(db, tenant_id),
            'current_month_start': datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        }
        
        # Calculate derived metrics
        metrics['storage_gb'] = metrics['storage_bytes'] / (1024 ** 3)
        
        return metrics
    
    def _count_file_uploads(self, db: Session, tenant_id: UUID) -> int:
        """Count file uploads for tenant in current month."""
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        count = db.query(func.count(UploadedFile.id)).filter(
            UploadedFile.tenant_id == tenant_id,
            UploadedFile.created_at >= month_start,
            UploadedFile.status == 'processed'
        ).scalar()
        
        return count or 0
    
    def _calculate_storage_usage(self, db: Session, tenant_id: UUID) -> int:
        """Calculate total storage usage in bytes."""
        from shared.models.file_models import UploadedFile
        
        total_bytes = db.query(func.coalesce(func.sum(UploadedFile.file_size), 0)).filter(
            UploadedFile.tenant_id == tenant_id,
            UploadedFile.status == 'processed'
        ).scalar()
        
        return int(total_bytes or 0)
    
    def _count_reports_generated(self, db: Session, tenant_id: UUID) -> int:
        """Count reports generated for tenant in current month."""
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        count = db.query(func.count(Report.id)).filter(
            Report.tenant_id == tenant_id,
            Report.created_at >= month_start,
            Report.status == 'completed'
        ).scalar()
        
        return count or 0
    
    def _count_api_calls(self, db: Session, tenant_id: UUID) -> int:
        """Count API calls for tenant in current month."""
        # This is a simplified version
        # In production, you would query an API logs table
        return 0
    
    def _estimate_ai_usage(self, db: Session, tenant_id: UUID) -> int:
        """Estimate AI token usage for tenant."""
        # This is a simplified estimation
        # In production, you would track actual AI usage
        return 0
    
    def _count_active_users(self, db: Session, tenant_id: UUID) -> int:
        """Count active users in tenant."""
        from shared.models.user_models import UserTenant, User
        
        count = db.query(func.count(UserTenant.user_id)).join(
            User, User.id == UserTenant.user_id
        ).filter(
            UserTenant.tenant_id == tenant_id,
            User.is_active == True
        ).scalar()
        
        return count or 0
    
    def _store_usage_metrics(self, db: Session, tenant_id: UUID, metrics: Dict[str, Any]):
        """Store usage metrics in database."""
        recorded_at = datetime.now()
        
        for metric_name, metric_value in metrics.items():
            if isinstance(metric_value, (int, float)):
                # Don't store datetime values
                if not isinstance(metric_value, datetime):
                    usage_record = UsageRecord(
                        tenant_id=tenant_id,
                        metric_name=metric_name,
                        metric_value=int(metric_value) if isinstance(metric_value, int) else float(metric_value),
                        recorded_at=recorded_at
                    )
                    db.add(usage_record)
        
        db.commit()
    
    def get_tenant_usage(self, tenant_id: UUID, timeframe: str = "month") -> Dict[str, Any]:
        """Get usage data for a tenant."""
        db: Session = next(get_db())
        
        try:
            # Calculate time range
            end_date = datetime.now()
            if timeframe == "day":
                start_date = end_date - timedelta(days=1)
            elif timeframe == "week":
                start_date = end_date - timedelta(weeks=1)
            elif timeframe == "month":
                start_date = end_date.replace(day=1)
            elif timeframe == "year":
                start_date = end_date.replace(month=1, day=1)
            else:
                start_date = end_date - timedelta(days=30)  # Default 30 days
            
            # Get usage records
            usage_records = db.query(UsageRecord).filter(
                UsageRecord.tenant_id == tenant_id,
                UsageRecord.recorded_at >= start_date,
                UsageRecord.recorded_at <= end_date
            ).order_by(UsageRecord.recorded_at).all()
            
            # Group by metric
            metrics = defaultdict(list)
            for record in usage_records:
                metrics[record.metric_name].append({
                    'value': record.metric_value,
                    'timestamp': record.recorded_at.isoformat()
                })
            
            # Get current metrics from cache or calculate
            current_metrics = self.usage_cache.get(str(tenant_id), {}).get('metrics', {})
            
            # Calculate totals
            totals = {}
            for metric_name, records in metrics.items():
                if records:
                    values = [r['value'] for r in records]
                    totals[metric_name] = {
                        'total': sum(values),
                        'average': sum(values) / len(values),
                        'max': max(values),
                        'min': min(values)
                    }
            
            return {
                'tenant_id': str(tenant_id),
                'timeframe': timeframe,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'current_metrics': current_metrics,
                'historical_data': dict(metrics),
                'totals': totals
            }
            
        except Exception as e:
            logger.error(f"Error getting tenant usage: {str(e)}")
            return {
                'tenant_id': str(tenant_id),
                'error': str(e)
            }
        finally:
            db.close()
    
    def record_usage(self, tenant_id: UUID, metric_name: str, metric_value: int, context: Optional[Dict] = None):
        """Record a usage event."""
        db: Session = next(get_db())
        
        try:
            usage_record = UsageRecord(
                tenant_id=tenant_id,
                metric_name=metric_name,
                metric_value=metric_value,
                recorded_at=datetime.now(),
                context=context
            )
            
            db.add(usage_record)
            db.commit()
            
            logger.debug(f"Recorded usage: {metric_name}={metric_value} for tenant {tenant_id}")
            
        except Exception as e:
            logger.error(f"Error recording usage: {str(e)}")
            db.rollback()
        finally:
            db.close()
    
    def get_usage_summary(self, tenant_id: UUID) -> Dict[str, Any]:
        """Get usage summary for a tenant."""
        # Try cache first
        if str(tenant_id) in self.usage_cache:
            cached_data = self.usage_cache[str(tenant_id)]
            if datetime.fromisoformat(cached_data['last_updated']) > datetime.now() - timedelta(minutes=5):
                return cached_data['metrics']
        
        # Calculate fresh metrics
        db: Session = next(get_db())
        try:
            metrics = self._calculate_tenant_metrics(db, tenant_id)
            
            # Update cache
            self.usage_cache[str(tenant_id)] = {
                'metrics': metrics,
                'last_updated': datetime.now().isoformat()
            }
            
            return metrics
        finally:
            db.close()


# Global usage tracker instance
usage_tracker = UsageTracker()