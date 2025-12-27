from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class MessageType(str, Enum):
    """Types of messages in the system."""
    
    # File processing messages
    FILE_UPLOADED = "file.uploaded"
    FILE_PROCESSED = "file.processed"
    FILE_VALIDATED = "file.validated"
    
    # Rule engine messages
    RULE_EVALUATION_REQUEST = "rule.evaluation.request"
    RULE_EVALUATION_COMPLETE = "rule.evaluation.complete"
    RULE_FINDINGS_GENERATED = "rule.findings.generated"
    
    # ML service messages
    ML_ANOMALY_REQUEST = "ml.anomaly.request"
    ML_ANOMALY_RESULT = "ml.anomaly.result"
    
    # LLM service messages
    LLM_ANALYSIS_REQUEST = "llm.analysis.request"
    LLM_ANALYSIS_RESULT = "llm.analysis.result"
    
    # Reporting messages
    REPORT_GENERATION_REQUEST = "report.generation.request"
    REPORT_GENERATION_COMPLETE = "report.generation.complete"
    
    # System messages
    TASK_FAILED = "system.task.failed"
    TASK_RETRY = "system.task.retry"
    SYSTEM_ALERT = "system.alert"


class MessagePriority(int, Enum):
    """Message priorities."""
    
    LOW = 0
    NORMAL = 5
    HIGH = 9
    CRITICAL = 10


class BaseMessage(BaseModel):
    """Base message format."""
    
    message_id: UUID = Field(default_factory=UUID)
    message_type: MessageType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source_service: str
    payload: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }


class FileUploadedMessage(BaseMessage):
    """Message for file upload events."""
    
    message_type: MessageType = MessageType.FILE_UPLOADED
    
    class Payload(BaseModel):
        tenant_id: UUID
        file_id: UUID
        filename: str
        file_path: str
        file_size: int
        file_type: str
        uploaded_by: UUID
    
    payload: Payload


class RuleEvaluationMessage(BaseMessage):
    """Message for rule evaluation events."""
    
    message_type: MessageType = MessageType.RULE_EVALUATION_REQUEST
    
    class Payload(BaseModel):
        tenant_id: UUID
        file_id: UUID
        rule_set_id: Optional[UUID] = None
        data_path: str
        user_id: UUID
    
    payload: Payload


class ReportGenerationMessage(BaseMessage):
    """Message for report generation events."""
    
    message_type: MessageType = MessageType.REPORT_GENERATION_REQUEST
    
    class Payload(BaseModel):
        tenant_id: UUID
        report_id: UUID
        report_type: str  # pdf, excel, html
        findings_ids: list[UUID]
        user_id: UUID
        include_explanations: bool = False
    
    payload: Payload


class TaskFailedMessage(BaseMessage):
    """Message for failed tasks."""
    
    message_type: MessageType = MessageType.TASK_FAILED
    
    class Payload(BaseModel):
        tenant_id: UUID
        task_id: str
        task_type: str
        error_message: str
        error_details: Optional[Dict[str, Any]] = None
        retry_count: int = 0
        max_retries: int = 3
    
    payload: Payload


def create_message(
    message_type: MessageType,
    source_service: str,
    payload: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
    priority: MessagePriority = MessagePriority.NORMAL
) -> Dict[str, Any]:
    """
    Create a standardized message.
    
    Args:
        message_type: Type of message
        source_service: Service that created the message
        payload: Message payload
        metadata: Additional metadata
        priority: Message priority
    
    Returns:
        Message dictionary
    """
    import uuid
    from datetime import datetime
    
    message = {
        "message_id": str(uuid.uuid4()),
        "message_type": message_type.value,
        "timestamp": datetime.utcnow().isoformat(),
        "source_service": source_service,
        "payload": payload,
        "metadata": metadata or {},
        "priority": priority.value
    }
    
    return message


def validate_message(message: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate message format.
    
    Args:
        message: Message to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    required_fields = ["message_id", "message_type", "timestamp", "source_service", "payload"]
    
    for field in required_fields:
        if field not in message:
            return False, f"Missing required field: {field}"
    
    # Validate message_type
    try:
        MessageType(message["message_type"])
    except ValueError:
        return False, f"Invalid message_type: {message['message_type']}"
    
    # Validate timestamp format
    try:
        datetime.fromisoformat(message["timestamp"].replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return False, f"Invalid timestamp format: {message['timestamp']}"
    
    return True, None