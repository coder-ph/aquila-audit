import json
from typing import Dict, Any
from uuid import UUID
import pika

from shared.messaging.rabbitmq_client import rabbitmq_client
from shared.messaging.message_formats import MessageType
from shared.utils.logging import logger

from services.worker_service.tasks import file_processing, rule_evaluation, report_generation


def handle_file_uploaded(message: Dict[str, Any], method):
    """Handle file uploaded messages."""
    try:
        payload = message.get("payload", {})
        tenant_id = payload.get("tenant_id")
        file_id = payload.get("file_id")
        
        if not tenant_id or not file_id:
            logger.error("Missing tenant_id or file_id in message")
            return
        
        logger.info(f"File uploaded event received: {file_id}", tenant_id=tenant_id)
        
        # Start file processing task
        file_processing.process_file_task.delay(file_id, tenant_id)
        
    except Exception as e:
        logger.error(f"Error handling file uploaded message: {str(e)}")


def handle_rule_evaluation(message: Dict[str, Any], method):
    """Handle rule evaluation messages."""
    try:
        payload = message.get("payload", {})
        tenant_id = payload.get("tenant_id")
        file_id = payload.get("file_id")
        
        if not tenant_id or not file_id:
            logger.error("Missing tenant_id or file_id in message")
            return
        
        logger.info(f"Rule evaluation request received: {file_id}", tenant_id=tenant_id)
        
        # Start rule evaluation task
        rule_evaluation.evaluate_rules_task.delay(file_id, tenant_id)
        
    except Exception as e:
        logger.error(f"Error handling rule evaluation message: {str(e)}")


def start_consumers():
    """Start RabbitMQ consumers."""
    logger.info("Starting RabbitMQ consumers")
    
    try:
        # Start consuming from file_processing queue
        rabbitmq_client.consume_messages(
            queue_name="file_processing",
            callback=handle_file_uploaded,
            auto_ack=False
        )
        
        # Start consuming from rule_evaluation queue
        rabbitmq_client.consume_messages(
            queue_name="rule_evaluation",
            callback=handle_rule_evaluation,
            auto_ack=False
        )
        
    except KeyboardInterrupt:
        logger.info("Stopping consumers")
    except Exception as e:
        logger.error(f"Error in consumers: {str(e)}")


if __name__ == "__main__":
    start_consumers()