"""
Event publisher for reporting service.
"""
from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime

from shared.messaging.message_formats import (
    MessageType,
    create_message,
    ReportGenerationMessage
)
from shared.messaging.rabbitmq_client import rabbitmq_client
from shared.utils.logging import logger


class ReportPublisher:
    """Publishes report-related events."""
    
    def __init__(self):
        self.service_name = "reporting_service"
    
    def publish_report_requested(
        self,
        tenant_id: str,
        report_id: str,
        report_type: str,
        findings_ids: list[str],
        user_id: str,
        include_explanations: bool = False
    ) -> bool:
        """
        Publish report requested event.
        
        Args:
            tenant_id: Tenant ID
            report_id: Report ID
            report_type: Report type
            findings_ids: List of finding IDs
            user_id: User ID
            include_explanations: Whether to include AI explanations
        
        Returns:
            True if published successfully
        """
        try:
            message = create_message(
                message_type=MessageType.REPORT_GENERATION_REQUEST,
                source_service=self.service_name,
                payload={
                    'tenant_id': tenant_id,
                    'report_id': report_id,
                    'report_type': report_type,
                    'findings_ids': findings_ids,
                    'user_id': user_id,
                    'include_explanations': include_explanations,
                    'requested_at': datetime.utcnow().isoformat()
                }
            )
            
            success = rabbitmq_client.publish_message(
                queue_name='report_generation_request',
                message=message,
                tenant_id=tenant_id,
                priority=5
            )
            
            if success:
                logger.info(f"Published report requested event: {report_id}")
            else:
                logger.error(f"Failed to publish report requested event: {report_id}")
            
            return success
        
        except Exception as e:
            logger.error(f"Error publishing report requested event: {str(e)}")
            return False
    
    def publish_report_completed(
        self,
        tenant_id: str,
        report_id: str,
        result: Dict[str, Any],
        user_id: str
    ) -> bool:
        """
        Publish report completed event.
        
        Args:
            tenant_id: Tenant ID
            report_id: Report ID
            result: Generation result
            user_id: User ID
        
        Returns:
            True if published successfully
        """
        try:
            message = create_message(
                message_type=MessageType.REPORT_GENERATION_COMPLETE,
                source_service=self.service_name,
                payload={
                    'tenant_id': tenant_id,
                    'report_id': report_id,
                    'result': result,
                    'user_id': user_id,
                    'completed_at': datetime.utcnow().isoformat()
                }
            )
            
            success = rabbitmq_client.publish_message(
                queue_name='report_generation_complete',
                message=message,
                tenant_id=tenant_id,
                priority=5
            )
            
            if success:
                logger.info(f"Published report completed event: {report_id}")
            else:
                logger.error(f"Failed to publish report completed event: {report_id}")
            
            return success
        
        except Exception as e:
            logger.error(f"Error publishing report completed event: {str(e)}")
            return False
    
    def publish_report_failed(
        self,
        tenant_id: str,
        report_id: str,
        error: str,
        user_id: str,
        retry_count: int = 0
    ) -> bool:
        """
        Publish report failed event.
        
        Args:
            tenant_id: Tenant ID
            report_id: Report ID
            error: Error message
            user_id: User ID
            retry_count: Number of retries attempted
        
        Returns:
            True if published successfully
        """
        try:
            message = create_message(
                message_type=MessageType.TASK_FAILED,
                source_service=self.service_name,
                payload={
                    'tenant_id': tenant_id,
                    'task_id': f"report_{report_id}",
                    'task_type': 'report_generation',
                    'error_message': error,
                    'error_details': {
                        'report_id': report_id,
                        'retry_count': retry_count
                    },
                    'user_id': user_id,
                    'failed_at': datetime.utcnow().isoformat()
                }
            )
            
            success = rabbitmq_client.publish_message(
                queue_name='task_failed',
                message=message,
                tenant_id=tenant_id,
                priority=9  # High priority for failures
            )
            
            if success:
                logger.error(f"Published report failed event: {report_id} - {error}")
            else:
                logger.error(f"Failed to publish report failed event: {report_id}")
            
            return success
        
        except Exception as e:
            logger.error(f"Error publishing report failed event: {str(e)}")
            return False
    
    def subscribe_to_findings_events(self) -> bool:
        """
        Subscribe to findings generated events.
        
        Returns:
            True if subscribed successfully
        """
        try:
            # Declare findings exchange
            rabbitmq_client.channel.exchange_declare(
                exchange='findings_events',
                exchange_type='topic',
                durable=True
            )
            
            # Declare queue for reporting service
            queue_name = 'reporting_service_findings'
            rabbitmq_client.declare_queue(queue_name)
            
            # Bind to findings events
            rabbitmq_client.channel.queue_bind(
                exchange='findings_events',
                queue=queue_name,
                routing_key='findings.generated.*'  # All findings generated events
            )
            
            logger.info("Subscribed to findings events")
            return True
        
        except Exception as e:
            logger.error(f"Failed to subscribe to findings events: {str(e)}")
            return False


# Global publisher instance
report_publisher = ReportPublisher()