"""
Alert manager for billing and usage alerts.
"""
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from shared.database.session import get_db
from shared.utils.logging import logger
from services.billing_service.config import config
from services.billing_service.alerts.notification_handler import notification_handler


class AlertManager:
    """Manages billing and usage alerts."""
    
    def __init__(self):
        self.running = False
        self.monitoring_thread = None
        self.active_alerts = {}  # Active alerts by tenant
        self.alert_history = []  # Historical alerts
    
    def start_monitoring(self):
        """Start alert monitoring."""
        if self.running:
            logger.warning("Alert monitoring already running")
            return
        
        self.running = True
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True
        )
        self.monitoring_thread.start()
        logger.info("Alert monitoring started")
    
    def stop_monitoring(self):
        """Stop alert monitoring."""
        self.running = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        logger.info("Alert monitoring stopped")
    
    def _monitoring_loop(self):
        """Background monitoring loop."""
        while self.running:
            try:
                self.check_all_alerts()
                time.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Error in alert monitoring loop: {str(e)}")
                time.sleep(30)
    
    def check_all_alerts(self):
        """Check all active alerts."""
        # Clean up old alerts
        self._cleanup_old_alerts()
        
        # Check for repeated alerts that need escalation
        self._check_alert_escalations()
    
    def _cleanup_old_alerts(self):
        """Clean up alerts older than 7 days."""
        cutoff = datetime.now() - timedelta(days=7)
        self.alert_history = [
            alert for alert in self.alert_history
            if datetime.fromisoformat(alert['created_at']) > cutoff
        ]
    
    def _check_alert_escalations(self):
        """Check if alerts need escalation."""
        for tenant_id, alerts in list(self.active_alerts.items()):
            for alert in alerts[:]:  # Copy for iteration
                created_at = datetime.fromisoformat(alert['created_at'])
                
                # Check if alert is old and unresolved
                if datetime.now() - created_at > timedelta(hours=24):
                    # Escalate to higher severity
                    if alert['severity'] == 'warning':
                        self.escalate_alert(tenant_id, alert, 'critical')
                    elif alert['severity'] == 'critical':
                        # Take additional action for critical alerts
                        self._handle_critical_alert(tenant_id, alert)
    
    def _handle_critical_alert(self, tenant_id: UUID, alert: Dict[str, Any]):
        """Handle critical alert escalation."""
        logger.critical(f"Critical alert unresolved for 24h: {alert['message']}")
        
        # Additional actions for unresolved critical alerts
        # 1. Send emergency notification
        # 2. Notify administrators
        # 3. Potentially suspend services
        
        pass
    
    def trigger_budget_alert(
        self,
        tenant_id: UUID,
        alert_type: str,
        severity: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Trigger a budget-related alert."""
        alert_id = f"budget_{alert_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        alert = {
            'alert_id': alert_id,
            'tenant_id': str(tenant_id),
            'type': alert_type,
            'severity': severity,
            'message': message,
            'details': details or {},
            'created_at': datetime.now().isoformat(),
            'status': 'active',
            'acknowledged': False,
            'resolved': False
        }
        
        # Store alert
        if str(tenant_id) not in self.active_alerts:
            self.active_alerts[str(tenant_id)] = []
        
        # Check if similar alert already exists
        similar_alerts = [
            a for a in self.active_alerts[str(tenant_id)]
            if a['type'] == alert_type and a['status'] == 'active'
        ]
        
        if not similar_alerts:
            self.active_alerts[str(tenant_id)].append(alert)
            self.alert_history.append(alert)
            
            # Send notification
            self._send_notification(alert)
            
            logger.warning(f"Budget alert triggered: {message}")
    
    def trigger_usage_alert(
        self,
        tenant_id: UUID,
        metric: str,
        usage_percentage: float,
        limit: float
    ):
        """Trigger a usage limit alert."""
        severity = 'warning' if usage_percentage < 90 else 'critical'
        
        alert = {
            'alert_id': f"usage_{metric}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            'tenant_id': str(tenant_id),
            'type': 'usage_limit',
            'severity': severity,
            'message': f"{metric.replace('_', ' ').title()} usage at {usage_percentage:.1f}% of limit ({limit})",
            'details': {
                'metric': metric,
                'usage_percentage': usage_percentage,
                'limit': limit
            },
            'created_at': datetime.now().isoformat(),
            'status': 'active',
            'acknowledged': False,
            'resolved': False
        }
        
        # Store alert
        if str(tenant_id) not in self.active_alerts:
            self.active_alerts[str(tenant_id)] = []
        
        self.active_alerts[str(tenant_id)].append(alert)
        self.alert_history.append(alert)
        
        # Send notification
        self._send_notification(alert)
        
        logger.warning(f"Usage alert triggered: {alert['message']}")
    
    def _send_notification(self, alert: Dict[str, Any]):
        """Send notification for an alert."""
        if config.email_enabled:
            notification_handler.send_email_alert(alert)
        
        # Could also send:
        # - Slack notifications
        # - SMS alerts
        # - Webhook notifications
    
    def acknowledge_alert(self, tenant_id: UUID, alert_id: str, user_id: UUID):
        """Acknowledge an alert."""
        if str(tenant_id) in self.active_alerts:
            for alert in self.active_alerts[str(tenant_id)]:
                if alert['alert_id'] == alert_id:
                    alert['acknowledged'] = True
                    alert['acknowledged_by'] = str(user_id)
                    alert['acknowledged_at'] = datetime.now().isoformat()
                    logger.info(f"Alert acknowledged: {alert_id}")
                    return True
        
        return False
    
    def resolve_alert(self, tenant_id: UUID, alert_id: str, user_id: UUID, resolution_notes: str = ""):
        """Resolve an alert."""
        if str(tenant_id) in self.active_alerts:
            for i, alert in enumerate(self.active_alerts[str(tenant_id)]):
                if alert['alert_id'] == alert_id:
                    alert['resolved'] = True
                    alert['resolved_by'] = str(user_id)
                    alert['resolved_at'] = datetime.now().isoformat()
                    alert['resolution_notes'] = resolution_notes
                    alert['status'] = 'resolved'
                    
                    # Move to history
                    self.alert_history.append(alert)
                    self.active_alerts[str(tenant_id)].pop(i)
                    
                    logger.info(f"Alert resolved: {alert_id}")
                    return True
        
        return False
    
    def escalate_alert(self, tenant_id: UUID, alert: Dict[str, Any], new_severity: str):
        """Escalate an alert to higher severity."""
        alert['severity'] = new_severity
        alert['escalated_at'] = datetime.now().isoformat()
        alert['escalation_reason'] = 'timeout'
        
        # Send new notification
        self._send_notification(alert)
        
        logger.warning(f"Alert escalated to {new_severity}: {alert['alert_id']}")
    
    def get_tenant_alerts(
        self,
        tenant_id: UUID,
        status: str = 'active',
        severity: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get alerts for a tenant."""
        alerts = []
        
        # Get active alerts
        if status == 'active' and str(tenant_id) in self.active_alerts:
            alerts.extend(self.active_alerts[str(tenant_id)])
        
        # Get historical alerts
        elif status == 'all' or status == 'resolved':
            tenant_history = [
                alert for alert in self.alert_history
                if alert['tenant_id'] == str(tenant_id)
            ]
            alerts.extend(tenant_history)
        
        # Filter by severity
        if severity:
            alerts = [alert for alert in alerts if alert['severity'] == severity]
        
        # Sort by creation time (newest first)
        alerts.sort(key=lambda x: x['created_at'], reverse=True)
        
        return alerts[:limit]
    
    def get_alert_summary(self, tenant_id: UUID) -> Dict[str, Any]:
        """Get alert summary for a tenant."""
        active_alerts = self.get_tenant_alerts(tenant_id, status='active')
        resolved_alerts = self.get_tenant_alerts(tenant_id, status='resolved')
        
        # Count by severity
        severity_counts = {'warning': 0, 'critical': 0}
        for alert in active_alerts:
            if alert['severity'] in severity_counts:
                severity_counts[alert['severity']] += 1
        
        # Count by type
        type_counts = {}
        for alert in active_alerts:
            alert_type = alert['type']
            type_counts[alert_type] = type_counts.get(alert_type, 0) + 1
        
        return {
            'tenant_id': str(tenant_id),
            'active_alert_count': len(active_alerts),
            'resolved_alert_count': len(resolved_alerts),
            'severity_counts': severity_counts,
            'type_counts': type_counts,
            'unacknowledged_count': len([a for a in active_alerts if not a['acknowledged']]),
            'latest_alert': active_alerts[0] if active_alerts else None
        }


# Global alert manager instance
alert_manager = AlertManager()