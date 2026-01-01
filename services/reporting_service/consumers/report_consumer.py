"""
RabbitMQ consumer for report generation requests.
"""
import json
from typing import Dict, Any
import pika

from shared.utils.logging import logger
from shared.messaging.rabbitmq_client import rabbitmq_client
from shared.messaging.message_formats import (
    MessageType,
    validate_message
)
from services.worker_service.tasks.report_generation import generate_report_task


class ReportConsumer:
    """Consumer for report generation messages."""
    
    def __init__(self):
        self.queue_name = 'report_generation_request'
        self.consuming = False
    
    def start_consuming(self) -> None:
        """Start consuming messages."""
        if self.consuming:
            logger.warning("Already consuming messages")
            return
        
        try:
            logger.info(f"Starting report consumer on queue: {self.queue_name}")
            
            # Declare queue
            rabbitmq_client.declare_queue(self.queue_name)
            
            # Start consuming
            rabbitmq_client.consume_messages(
                queue_name=self.queue_name,
                callback=self.process_message,
                auto_ack=False
            )
            
            self.consuming = True
            
        except Exception as e:
            logger.error(f"Failed to start report consumer: {str(e)}")
            self.consuming = False
    
    def stop_consuming(self) -> None:
        """Stop consuming messages."""
        if not self.consuming:
            return
        
        try:
            rabbitmq_client.channel.stop_consuming()
            self.consuming = False
            logger.info("Stopped report consumer")
        
        except Exception as e:
            logger.error(f"Failed to stop report consumer: {str(e)}")
    
    def process_message(self, message: Dict[str, Any], method: pika.DeliveryMode) -> None:
        """
        Process incoming message.
        
        Args:
            message: Message data
            method: Delivery method
        """
        try:
            # Validate message
            is_valid, error = validate_message(message)
            if not is_valid:
                logger.error(f"Invalid message format: {error}")
                method.reject(requeue=False)
                return
            
            message_type = MessageType(message['message_type'])
            
            if message_type == MessageType.REPORT_GENERATION_REQUEST:
                self.handle_report_request(message)
            
            elif message_type == MessageType.RULE_FINDINGS_GENERATED:
                self.handle_findings_generated(message)
            
            else:
                logger.warning(f"Unhandled message type: {message_type}")
            
            # Acknowledge message
            method.ack()
            
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            # Reject and don't requeue (send to DLQ)
            method.reject(requeue=False)
    
    def handle_report_request(self, message: Dict[str, Any]) -> None:
        """
        Handle report generation request.
        
        Args:
            message: Message data
        """
        try:
            payload = message.get('payload', {})
            metadata = message.get('metadata', {})
            
            tenant_id = payload.get('tenant_id')
            report_id = payload.get('report_id')
            
            logger.info(f"Processing report generation request: {report_id} for tenant: {tenant_id}")
            
            # Trigger Celery task
            task_result = generate_report_task.apply_async(
                args=[payload, message],
                queue='report_generation',
                kwargs={
                    'tenant_id': tenant_id,
                    'priority': metadata.get('priority', 5)
                }
            )
            
            logger.info(f"Report generation task queued: {task_result.id} for report: {report_id}")
        
        except Exception as e:
            logger.error(f"Failed to handle report request: {str(e)}")
            raise
    
    def handle_findings_generated(self, message: Dict[str, Any]) -> None:
        """
        Handle rule findings generated event.
        
        Args:
            message: Message data
        """
        try:
            payload = message.get('payload', {})
            
            tenant_id = payload.get('tenant_id')
            file_id = payload.get('file_id')
            findings_ids = payload.get('findings_ids', [])
            
            logger.info(f"Findings generated for file: {file_id}, count: {len(findings_ids)}")
            
            # Check if auto-report generation is enabled
            # In production, this would check tenant preferences
            if len(findings_ids) > 0:
                self.trigger_auto_report(
                    tenant_id=tenant_id,
                    file_id=file_id,
                    findings_ids=findings_ids
                )
        
        except Exception as e:
            logger.error(f"Failed to handle findings generated event: {str(e)}")
    
    def trigger_auto_report(
        self,
        tenant_id: str,
        file_id: str,
        findings_ids: list[str]
    ) -> None:
        """
        Trigger automatic report generation.
        
        Args:
            tenant_id: Tenant ID
            file_id: File ID
            findings_ids: List of finding IDs
        """
        import uuid
        from datetime import datetime
        
        try:
            report_id = str(uuid.uuid4())
            
            report_data = {
                'tenant_id': tenant_id,
                'report_id': report_id,
                'report_type': 'pdf',
                'findings_ids': findings_ids,
                'user_id': 'system',  # System-generated
                'include_explanations': True,
                'auto_generated': True,
                'triggered_by': 'findings_generated',
                'source_file_id': file_id,
                'generated_at': datetime.utcnow().isoformat()
            }
            
            # Create message for auto-report
            from shared.messaging.message_formats import create_message
            
            message = create_message(
                message_type=MessageType.REPORT_GENERATION_REQUEST,
                source_service="reporting_service_auto",
                payload=report_data,
                metadata={'auto_generated': True}
            )
            
            # Publish to queue
            rabbitmq_client.publish_message(
                queue_name='report_generation_request',
                message=message,
                tenant_id=tenant_id,
                priority=3  # Lower priority for auto-generated reports
            )
            
            logger.info(f"Auto-report triggered: {report_id} for findings from file: {file_id}")
        
        except Exception as e:
            logger.error(f"Failed to trigger auto-report: {str(e)}")


# Global consumer instance
report_consumer = ReportConsumer()