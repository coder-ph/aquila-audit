from typing import Any, Dict, Optional
from uuid import UUID

from shared.messaging.rabbitmq_client import rabbitmq_client
from shared.messaging.message_formats import (
    MessageType,
    MessagePriority,
    create_message,
    validate_message
)
from shared.utils.logging import logger


class EventPublisher:
    """Publisher for system events."""
    
    def __init__(self):
        self.client = rabbitmq_client
    
    def publish(
        self,
        queue_name: str,
        message_type: MessageType,
        source_service: str,
        payload: Dict[str, Any],
        tenant_id: Optional[UUID] = None,
        priority: MessagePriority = MessagePriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Publish event to message queue.
        
        Args:
            queue_name: Name of the queue
            message_type: Type of message
            source_service: Service that created the message
            payload: Message payload
            tenant_id: Tenant ID
            priority: Message priority
            metadata: Additional metadata
        
        Returns:
            True if event was published successfully
        """
        # Create message
        message = create_message(
            message_type=message_type,
            source_service=source_service,
            payload=payload,
            metadata=metadata,
            priority=priority
        )
        
        # Validate message
        is_valid, error = validate_message(message)
        if not is_valid:
            logger.error(f"Invalid message format: {error}")
            return False
        
        # Publish to queue
        success = self.client.publish_message(
            queue_name=queue_name,
            message=message,
            tenant_id=tenant_id,
            priority=priority.value
        )
        
        if success:
            logger.debug(
                f"Event published: {message_type.value} -> {queue_name}",
                tenant_id=str(tenant_id) if tenant_id else None
            )
        else:
            logger.error(
                f"Failed to publish event: {message_type.value}",
                tenant_id=str(tenant_id) if tenant_id else None
            )
        
        return success
    
    def publish_file_uploaded(
        self,
        tenant_id: UUID,
        file_id: UUID,
        filename: str,
        file_path: str,
        file_size: int,
        file_type: str,
        uploaded_by: UUID
    ) -> bool:
        """
        Publish file uploaded event.
        
        Args:
            tenant_id: Tenant ID
            file_id: File ID
            filename: Original filename
            file_path: Path to uploaded file
            file_size: File size in bytes
            file_type: File type/extension
            uploaded_by: User who uploaded the file
        
        Returns:
            True if event was published
        """
        payload = {
            "tenant_id": str(tenant_id),
            "file_id": str(file_id),
            "filename": filename,
            "file_path": file_path,
            "file_size": file_size,
            "file_type": file_type,
            "uploaded_by": str(uploaded_by)
        }
        
        return self.publish(
            queue_name="file_processing",
            message_type=MessageType.FILE_UPLOADED,
            source_service="api_gateway",
            payload=payload,
            tenant_id=tenant_id
        )
    
    def publish_rule_evaluation(
        self,
        tenant_id: UUID,
        file_id: UUID,
        data_path: str,
        user_id: UUID,
        rule_set_id: Optional[UUID] = None
    ) -> bool:
        """
        Publish rule evaluation request.
        
        Args:
            tenant_id: Tenant ID
            file_id: File ID
            data_path: Path to processed data
            user_id: User requesting evaluation
            rule_set_id: Optional rule set ID
        
        Returns:
            True if event was published
        """
        payload = {
            "tenant_id": str(tenant_id),
            "file_id": str(file_id),
            "rule_set_id": str(rule_set_id) if rule_set_id else None,
            "data_path": data_path,
            "user_id": str(user_id)
        }
        
        return self.publish(
            queue_name="rule_evaluation",
            message_type=MessageType.RULE_EVALUATION_REQUEST,
            source_service="api_gateway",
            payload=payload,
            tenant_id=tenant_id,
            priority=MessagePriority.HIGH
        )
    
    def publish_report_generation(
        self,
        tenant_id: UUID,
        report_id: UUID,
        report_type: str,
        findings_ids: list[UUID],
        user_id: UUID,
        include_explanations: bool = False
    ) -> bool:
        """
        Publish report generation request.
        
        Args:
            tenant_id: Tenant ID
            report_id: Report ID
            report_type: Type of report (pdf, excel, html)
            findings_ids: List of finding IDs to include
            user_id: User requesting report
            include_explanations: Whether to include AI explanations
        
        Returns:
            True if event was published
        """
        payload = {
            "tenant_id": str(tenant_id),
            "report_id": str(report_id),
            "report_type": report_type,
            "findings_ids": [str(fid) for fid in findings_ids],
            "user_id": str(user_id),
            "include_explanations": include_explanations
        }
        
        return self.publish(
            queue_name="report_generation",
            message_type=MessageType.REPORT_GENERATION_REQUEST,
            source_service="api_gateway",
            payload=payload,
            tenant_id=tenant_id
        )
    
    def publish_task_failed(
        self,
        tenant_id: UUID,
        task_id: str,
        task_type: str,
        error_message: str,
        error_details: Optional[Dict[str, Any]] = None,
        retry_count: int = 0
    ) -> bool:
        """
        Publish task failed event.
        
        Args:
            tenant_id: Tenant ID
            task_id: Task identifier
            task_type: Type of task
            error_message: Error message
            error_details: Additional error details
            retry_count: Current retry count
        
        Returns:
            True if event was published
        """
        payload = {
            "tenant_id": str(tenant_id),
            "task_id": task_id,
            "task_type": task_type,
            "error_message": error_message,
            "error_details": error_details or {},
            "retry_count": retry_count,
            "max_retries": 3
        }
        
        return self.publish(
            queue_name="task_failed",
            message_type=MessageType.TASK_FAILED,
            source_service="system",
            payload=payload,
            tenant_id=tenant_id,
            priority=MessagePriority.CRITICAL
        )


# Global event publisher instance
event_publisher = EventPublisher()