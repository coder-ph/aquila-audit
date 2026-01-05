"""
RabbitMQ consumer for billing events.
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
from services.billing_service.tracking.usage_tracker import usage_tracker
from services.billing_service.tracking.cost_calculator import cost_calculator
from services.billing_service.alerts.alert_manager import alert_manager


class BillingConsumer:
    """Consumer for billing-related messages."""
    
    def __init__(self):
        self.queue_name = 'billing_events'
        self.consuming = False
    
    def start_consuming(self) -> None:
        """Start consuming messages."""
        if self.consuming:
            logger.warning("Already consuming messages")
            return
        
        try:
            logger.info(f"Starting billing consumer on queue: {self.queue_name}")
            
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
            logger.error(f"Failed to start billing consumer: {str(e)}")
            self.consuming = False
    
    def stop_consuming(self) -> None:
        """Stop consuming messages."""
        if not self.consuming:
            return
        
        try:
            rabbitmq_client.channel.stop_consuming()
            self.consuming = False
            logger.info("Stopped billing consumer")
        
        except Exception as e:
            logger.error(f"Failed to stop billing consumer: {str(e)}")
    
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
            payload = message.get('payload', {})
            
            # Handle different message types
            if message_type == MessageType.FILE_UPLOADED:
                self.handle_file_uploaded(payload)
            
            elif message_type == MessageType.FILE_PROCESSED:
                self.handle_file_processed(payload)
            
            elif message_type == MessageType.RULE_EVALUATION_COMPLETE:
                self.handle_rule_evaluation(payload)
            
            elif message_type == MessageType.REPORT_GENERATION_COMPLETE:
                self.handle_report_generated(payload)
            
            elif message_type == MessageType.LLM_ANALYSIS_RESULT:
                self.handle_llm_analysis(payload)
            
            else:
                logger.debug(f"Unhandled message type: {message_type}")
            
            # Acknowledge message
            method.ack()
            
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            # Reject and don't requeue (send to DLQ)
            method.reject(requeue=False)
    
    def handle_file_uploaded(self, payload: Dict[str, Any]) -> None:
        """Handle file uploaded event."""
        try:
            tenant_id = payload.get('tenant_id')
            file_size = payload.get('file_size', 0)
            
            if tenant_id and file_size > 0:
                # Record storage usage
                usage_tracker.record_usage(
                    tenant_id=tenant_id,
                    metric_name='storage_bytes',
                    metric_value=file_size,
                    context={
                        'file_id': payload.get('file_id'),
                        'event': 'file_uploaded'
                    }
                )
                
                logger.debug(f"Recorded storage usage for tenant {tenant_id}: {file_size} bytes")
        
        except Exception as e:
            logger.error(f"Error handling file uploaded event: {str(e)}")
    
    def handle_file_processed(self, payload: Dict[str, Any]) -> None:
        """Handle file processed event."""
        try:
            tenant_id = payload.get('tenant_id')
            
            if tenant_id:
                # Record file processing
                usage_tracker.record_usage(
                    tenant_id=tenant_id,
                    metric_name='file_uploads',
                    metric_value=1,
                    context={
                        'file_id': payload.get('file_id'),
                        'event': 'file_processed'
                    }
                )
                
                logger.debug(f"Recorded file processing for tenant {tenant_id}")
        
        except Exception as e:
            logger.error(f"Error handling file processed event: {str(e)}")
    
    def handle_rule_evaluation(self, payload: Dict[str, Any]) -> None:
        """Handle rule evaluation event."""
        try:
            tenant_id = payload.get('tenant_id')
            
            if tenant_id:
                # Record API call for rule evaluation
                usage_tracker.record_usage(
                    tenant_id=tenant_id,
                    metric_name='api_calls',
                    metric_value=1,
                    context={
                        'event': 'rule_evaluation',
                        'rule_count': payload.get('rule_count', 1)
                    }
                )
        
        except Exception as e:
            logger.error(f"Error handling rule evaluation event: {str(e)}")
    
    def handle_report_generated(self, payload: Dict[str, Any]) -> None:
        """Handle report generated event."""
        try:
            tenant_id = payload.get('tenant_id')
            report_type = payload.get('report_type', 'pdf')
            
            if tenant_id:
                # Record report generation
                usage_tracker.record_usage(
                    tenant_id=tenant_id,
                    metric_name='reports_generated',
                    metric_value=1,
                    context={
                        'report_type': report_type,
                        'event': 'report_generated'
                    }
                )
                
                # Also count as API call
                usage_tracker.record_usage(
                    tenant_id=tenant_id,
                    metric_name='api_calls',
                    metric_value=1,
                    context={
                        'event': 'report_generation',
                        'report_type': report_type
                    }
                )
        
        except Exception as e:
            logger.error(f"Error handling report generated event: {str(e)}")
    
    def handle_llm_analysis(self, payload: Dict[str, Any]) -> None:
        """Handle LLM analysis event."""
        try:
            tenant_id = payload.get('tenant_id')
            token_count = payload.get('token_count', 0)
            
            if tenant_id and token_count > 0:
                # Record AI token usage
                usage_tracker.record_usage(
                    tenant_id=tenant_id,
                    metric_name='ai_tokens_used',
                    metric_value=token_count,
                    context={
                        'event': 'llm_analysis',
                        'model': payload.get('model', 'unknown')
                    }
                )
        
        except Exception as e:
            logger.error(f"Error handling LLM analysis event: {str(e)}")
    
    def check_usage_limits(self, tenant_id: str, metric: str, current_usage: float):
        """Check usage against limits and trigger alerts if needed."""
        try:
            # Get subscription limits
            from shared.database.session import get_db
            from shared.models.billing_models import Subscription, BillingPlan
            
            db = next(get_db())
            
            subscription = db.query(Subscription).filter(
                Subscription.tenant_id == tenant_id,
                Subscription.status == 'active'
            ).first()
            
            if not subscription:
                return
            
            plan = subscription.billing_plan
            
            # Check specific limits
            limits = {
                'storage_gb': plan.max_storage_gb,
                'file_uploads': plan.max_files_per_month,
                'api_calls': plan.max_api_calls
            }
            
            if metric in limits and limits[metric]:
                limit = limits[metric]
                usage_percentage = (current_usage / limit) * 100
                
                # Trigger alert if over 80%
                if usage_percentage > 80:
                    alert_manager.trigger_usage_alert(
                        tenant_id=tenant_id,
                        metric=metric,
                        usage_percentage=usage_percentage,
                        limit=limit
                    )
        
        except Exception as e:
            logger.error(f"Error checking usage limits: {str(e)}")


# Global billing consumer instance
billing_consumer = BillingConsumer()