import pika
import json
from typing import Any, Dict, Optional, Callable
from uuid import UUID
from tenacity import retry, stop_after_attempt, wait_exponential

from shared.utils.config import settings
from shared.utils.logging import logger


class RabbitMQClient:
    """RabbitMQ client for message queue operations."""
    
    def __init__(self):
        self.connection_url = str(settings.rabbitmq_url)
        self.connection: Optional[pika.BlockingConnection] = None
        self.channel: Optional[pika.adapters.blocking_connection.BlockingChannel] = None
        self.connected = False
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def connect(self) -> None:
        """
        Connect to RabbitMQ server.
        
        Raises:
            ConnectionError: If connection fails
        """
        try:
            parameters = pika.URLParameters(self.connection_url)
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            self.connected = True
            
            # Configure quality of service
            self.channel.basic_qos(prefetch_count=1)
            
            logger.info("Connected to RabbitMQ")
        
        except Exception as e:
            self.connected = False
            logger.error(f"Failed to connect to RabbitMQ: {str(e)}")
            raise ConnectionError(f"RabbitMQ connection failed: {str(e)}")
    
    def disconnect(self) -> None:
        """Disconnect from RabbitMQ."""
        if self.channel and self.channel.is_open:
            self.channel.close()
        
        if self.connection and self.connection.is_open:
            self.connection.close()
        
        self.connected = False
        logger.info("Disconnected from RabbitMQ")
    
    def ensure_connection(self) -> None:
        """Ensure connection is established."""
        if not self.connected or not self.connection or self.connection.is_closed:
            self.connect()
    
    def declare_queue(
        self,
        queue_name: str,
        durable: bool = True,
        arguments: Optional[Dict] = None
    ) -> None:
        """
        Declare a queue.
        
        Args:
            queue_name: Name of the queue
            durable: Whether queue survives broker restart
            arguments: Additional queue arguments
        """
        self.ensure_connection()
        
        if arguments is None:
            arguments = {}
        
        # Add dead letter exchange arguments
        dlx_arguments = {
            'x-dead-letter-exchange': f'{queue_name}_dlx',
            'x-dead-letter-routing-key': f'{queue_name}_dlq'
        }
        arguments.update(dlx_arguments)
        
        self.channel.queue_declare(
            queue=queue_name,
            durable=durable,
            arguments=arguments
        )
        
        # Declare dead letter queue
        dlx_name = f'{queue_name}_dlx'
        dlq_name = f'{queue_name}_dlq'
        
        self.channel.exchange_declare(
            exchange=dlx_name,
            exchange_type='direct',
            durable=True
        )
        
        self.channel.queue_declare(
            queue=dlq_name,
            durable=True
        )
        
        self.channel.queue_bind(
            exchange=dlx_name,
            queue=dlq_name,
            routing_key=dlq_name
        )
        
        logger.debug(f"Queue declared: {queue_name}")
    
    def publish_message(
        self,
        queue_name: str,
        message: Dict[str, Any],
        tenant_id: Optional[UUID] = None,
        priority: int = 0
    ) -> bool:
        """
        Publish message to queue.
        
        Args:
            queue_name: Name of the queue
            message: Message to publish
            tenant_id: Tenant ID for isolation
            priority: Message priority (0-9)
        
        Returns:
            True if message was published successfully
        """
        try:
            self.ensure_connection()
            
            # Add tenant context to message
            message_with_context = {
                **message,
                "metadata": {
                    "tenant_id": str(tenant_id) if tenant_id else None,
                    "timestamp": json.dumps(
                        {"timestamp": "TODO: Add timestamp"},
                        default=str
                    ),
                    "priority": priority
                }
            }
            
            # Declare queue if it doesn't exist
            self.declare_queue(queue_name)
            
            # Publish message
            self.channel.basic_publish(
                exchange='',
                routing_key=queue_name,
                body=json.dumps(message_with_context),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Make message persistent
                    priority=priority,
                    content_type='application/json'
                )
            )
            
            logger.debug(
                f"Message published to {queue_name}",
                tenant_id=str(tenant_id) if tenant_id else None
            )
            return True
        
        except Exception as e:
            logger.error(
                f"Failed to publish message to {queue_name}: {str(e)}",
                tenant_id=str(tenant_id) if tenant_id else None
            )
            return False
    
    def consume_messages(
        self,
        queue_name: str,
        callback: Callable[[Dict[str, Any], pika.DeliveryMode], None],
        auto_ack: bool = False
    ) -> None:
        """
        Consume messages from queue.
        
        Args:
            queue_name: Name of the queue
            callback: Callback function to process messages
            auto_ack: Whether to auto-acknowledge messages
        """
        self.ensure_connection()
        
        # Declare queue
        self.declare_queue(queue_name)
        
        def wrapped_callback(ch, method, properties, body):
            """Wrapper callback with error handling."""
            try:
                message = json.loads(body.decode('utf-8'))
                callback(message, method)
                
                if not auto_ack:
                    ch.basic_ack(delivery_tag=method.delivery_tag)
            
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse message: {str(e)}")
                if not auto_ack:
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                if not auto_ack:
                    # Negative acknowledge and don't requeue (send to DLQ)
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        
        # Start consuming
        self.channel.basic_consume(
            queue=queue_name,
            on_message_callback=wrapped_callback,
            auto_ack=auto_ack
        )
        
        logger.info(f"Started consuming from queue: {queue_name}")
        
        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("Stopping message consumption")
            self.channel.stop_consuming()
    
    def get_queue_stats(self, queue_name: str) -> Optional[Dict[str, Any]]:
        """
        Get queue statistics.
        
        Args:
            queue_name: Name of the queue
        
        Returns:
            Queue statistics or None
        """
        try:
            self.ensure_connection()
            
            queue = self.channel.queue_declare(
                queue=queue_name,
                passive=True  # Just check queue exists
            )
            
            return {
                'name': queue_name,
                'message_count': queue.method.message_count,
                'consumer_count': queue.method.consumer_count
            }
        
        except Exception as e:
            logger.error(f"Failed to get stats for queue {queue_name}: {str(e)}")
            return None
    
    def purge_queue(self, queue_name: str) -> bool:
        """
        Purge all messages from queue.
        
        Args:
            queue_name: Name of the queue
        
        Returns:
            True if queue was purged
        """
        try:
            self.ensure_connection()
            self.channel.queue_purge(queue=queue_name)
            logger.info(f"Purged queue: {queue_name}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to purge queue {queue_name}: {str(e)}")
            return False


# Global RabbitMQ client instance
rabbitmq_client = RabbitMQClient()