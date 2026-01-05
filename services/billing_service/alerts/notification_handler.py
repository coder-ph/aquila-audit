"""
Notification handler for billing alerts.
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Any, Optional
from uuid import UUID

from shared.utils.logging import logger
from services.billing_service.config import config


class NotificationHandler:
    """Handles notifications for billing alerts."""
    
    def __init__(self):
        self.email_enabled = config.email_enabled
        
    def send_email_alert(self, alert: Dict[str, Any]) -> bool:
        """Send email notification for an alert."""
        if not self.email_enabled:
            logger.debug("Email notifications are disabled")
            return False
        
        try:
            # Get tenant information
            from shared.database.session import get_db
            from shared.models.user_models import Tenant
            
            db = next(get_db())
            tenant = db.query(Tenant).filter(Tenant.id == UUID(alert['tenant_id'])).first()
            
            if not tenant:
                logger.error(f"Tenant not found for alert: {alert['tenant_id']}")
                return False
            
            # Get tenant admin emails
            admin_emails = self._get_tenant_admin_emails(db, UUID(alert['tenant_id']))
            
            if not admin_emails:
                logger.warning(f"No admin emails found for tenant {alert['tenant_id']}")
                return False
            
            # Create email
            subject = f"[Aquila Audit] {alert['severity'].upper()} Alert: {alert['type']}"
            
            # Create HTML email
            html_content = self._create_alert_html(alert, tenant)
            text_content = self._create_alert_text(alert, tenant)
            
            # Send to each admin
            success_count = 0
            for email in admin_emails:
                if self._send_email(email, subject, text_content, html_content):
                    success_count += 1
            
            logger.info(f"Alert email sent to {success_count}/{len(admin_emails)} admins for tenant {tenant.slug}")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"Error sending email alert: {str(e)}")
            return False
    
    def _get_tenant_admin_emails(self, db, tenant_id: UUID) -> List[str]:
        """Get admin email addresses for a tenant."""
        from shared.models.user_models import UserTenant, User
        
        admins = db.query(User.email).join(
            UserTenant, User.id == UserTenant.user_id
        ).filter(
            UserTenant.tenant_id == tenant_id,
            User.is_active == True,
            UserTenant.role.in_(['admin', 'owner'])
        ).all()
        
        return [admin[0] for admin in admins]
    
    def _create_alert_html(self, alert: Dict[str, Any], tenant: Any) -> str:
        """Create HTML content for alert email."""
        severity_colors = {
            'warning': '#F39C12',
            'critical': '#E74C3C'
        }
        
        color = severity_colors.get(alert['severity'], '#3498DB')
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: {color}; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: #f9f9f9; padding: 20px; border: 1px solid #ddd; border-top: none; }}
                .alert-details {{ background-color: white; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                .footer {{ text-align: center; color: #777; font-size: 12px; margin-top: 20px; }}
                .button {{ display: inline-block; padding: 10px 20px; background-color: {color}; color: white; text-decoration: none; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{alert['severity'].upper()} ALERT</h1>
                    <h2>{alert['type'].replace('_', ' ').title()}</h2>
                </div>
                
                <div class="content">
                    <p><strong>Tenant:</strong> {tenant.name} ({tenant.slug})</p>
                    <p><strong>Alert ID:</strong> {alert['alert_id']}</p>
                    <p><strong>Time:</strong> {alert['created_at']}</p>
                    
                    <div class="alert-details">
                        <h3>Alert Details</h3>
                        <p>{alert['message']}</p>
                        
                        <h4>Details:</h4>
                        <pre>{self._format_details(alert['details'])}</pre>
                    </div>
                    
                    <p>
                        <a href="https://app.aquila-audit.com/admin/tenants/{tenant.id}/billing" class="button">
                            View Billing Dashboard
                        </a>
                    </p>
                    
                    <p>
                        To acknowledge or resolve this alert, please visit the admin dashboard.
                    </p>
                </div>
                
                <div class="footer">
                    <p>This is an automated message from Aquila Audit Billing Service.</p>
                    <p>If you believe this alert was sent in error, please contact support.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _create_alert_text(self, alert: Dict[str, Any], tenant: Any) -> str:
        """Create plain text content for alert email."""
        text = f"""
        {alert['severity'].upper()} ALERT: {alert['type'].replace('_', ' ').title()}
        {'=' * 50}
        
        Tenant: {tenant.name} ({tenant.slug})
        Alert ID: {alert['alert_id']}
        Time: {alert['created_at']}
        
        Message: {alert['message']}
        
        Details:
        {self._format_details(alert['details'])}
        
        Action Required:
        Please review this alert in the Aquila Audit admin dashboard.
        URL: https://app.aquila-audit.com/admin/tenants/{tenant.id}/billing
        
        --
        This is an automated message from Aquila Audit Billing Service.
        """
        
        return text
    
    def _format_details(self, details: Dict[str, Any]) -> str:
        """Format details dictionary for display."""
        formatted = []
        for key, value in details.items():
            formatted.append(f"  {key}: {value}")
        return "\n".join(formatted)
    
    def _send_email(self, to_email: str, subject: str, text_content: str, html_content: str) -> bool:
        """Send an email."""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = config.email_from
            msg['To'] = to_email
            
            # Attach parts
            part1 = MIMEText(text_content, 'plain')
            part2 = MIMEText(html_content, 'html')
            
            msg.attach(part1)
            msg.attach(part2)
            
            # Send email
            with smtplib.SMTP(config.email_smtp_host, config.email_smtp_port) as server:
                server.starttls()
                # In production, you would use proper authentication
                # server.login(config.email_username, config.email_password)
                server.send_message(msg)
            
            logger.debug(f"Email sent to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending email to {to_email}: {str(e)}")
            return False
    
    def send_monthly_invoice(self, tenant_id: UUID, invoice_data: Dict[str, Any]) -> bool:
        """Send monthly invoice email."""
        # Implementation for monthly invoices
        # Similar to send_email_alert but with invoice template
        pass
    
    def send_payment_failed(self, tenant_id: UUID, payment_data: Dict[str, Any]) -> bool:
        """Send payment failed notification."""
        # Implementation for payment failure notifications
        pass


# Global notification handler instance
notification_handler = NotificationHandler()