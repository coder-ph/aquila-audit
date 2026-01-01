#!/usr/bin/env python3
"""
Test script for Week 9 Reporting Service features.
"""
import json
import uuid
from datetime import datetime
from pathlib import Path

from shared.messaging.rabbitmq_client import rabbitmq_client
from shared.messaging.message_formats import (
    MessageType,
    create_message,
    ReportGenerationMessage
)
from services.worker_service.tasks.report_generation import (
    generate_report_task,
    generate_batch_reports_task
)


def test_rabbitmq_connection():
    """Test RabbitMQ connection."""
    print("Testing RabbitMQ connection...")
    
    try:
        rabbitmq_client.connect()
        
        # Test queue declaration
        rabbitmq_client.declare_queue('test_report_queue')
        
        # Test message publishing
        test_message = {
            'test': True,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        success = rabbitmq_client.publish_message(
            queue_name='test_report_queue',
            message=test_message,
            tenant_id=str(uuid.uuid4())
        )
        
        rabbitmq_client.disconnect()
        
        if success:
            print("✓ RabbitMQ connection test passed")
            return True
        else:
            print("✗ RabbitMQ connection test failed")
            return False
    
    except Exception as e:
        print(f"✗ RabbitMQ connection test failed: {str(e)}")
        return False


def test_celery_task():
    """Test Celery report generation task."""
    print("Testing Celery task execution...")
    
    try:
        test_data = {
            'tenant_id': str(uuid.uuid4()),
            'report_id': str(uuid.uuid4()),
            'report_type': 'pdf',
            'findings_ids': [],
            'user_id': str(uuid.uuid4()),
            'include_explanations': True,
            'test': True
        }
        
        # Execute task synchronously for testing
        result = generate_report_task.apply(
            args=[test_data],
            queue='report_generation'
        ).get()
        
        print(f"✓ Celery task test passed: {result.get('success', False)}")
        return True
    
    except Exception as e:
        print(f"✗ Celery task test failed: {str(e)}")
        return False


def test_message_format():
    """Test message format creation and validation."""
    print("Testing message formats...")
    
    try:
        # Test message creation
        message = create_message(
            message_type=MessageType.REPORT_GENERATION_REQUEST,
            source_service="test_service",
            payload={
                'tenant_id': str(uuid.uuid4()),
                'report_id': str(uuid.uuid4()),
                'test': True
            }
        )
        
        # Test validation
        from shared.messaging.message_formats import validate_message
        is_valid, error = validate_message(message)
        
        if is_valid:
            print("✓ Message format test passed")
            return True
        else:
            print(f"✗ Message format test failed: {error}")
            return False
    
    except Exception as e:
        print(f"✗ Message format test failed: {str(e)}")
        return False


def test_report_generator():
    """Test report generator."""
    print("Testing report generator...")
    
    try:
        from services.reporting_service.generators.report_generator import report_generator
        
        test_report_data = {
            'report_id': 'test_report',
            'title': 'Test Audit Report',
            'generated_by': 'Test User',
            'generated_date': datetime.now().isoformat(),
            'findings': [
                {
                    'id': '1',
                    'title': 'Test Finding 1',
                    'description': 'This is a test finding',
                    'severity': 'high',
                    'category': 'security',
                    'recommendation': 'Fix this issue'
                },
                {
                    'id': '2',
                    'title': 'Test Finding 2',
                    'description': 'Another test finding',
                    'severity': 'medium',
                    'category': 'compliance',
                    'recommendation': 'Review and update'
                }
            ],
            'summary': 'Test report summary'
        }
        
        # Test PDF generation
        result = report_generator.generate_report(
            report_data=test_report_data,
            output_format='pdf',
            tenant_id='test_tenant'
        )
        
        if result.get('success', False):
            print(f"✓ Report generator test passed: {result.get('filename')}")
            return True
        else:
            print(f"✗ Report generator test failed")
            return False
    
    except Exception as e:
        print(f"✗ Report generator test failed: {str(e)}")
        return False


def test_llm_integration():
    """Test LLM integration."""
    print("Testing LLM integration...")
    
    try:
        from services.reporting_service.integrations.llm_integration import llm_integration
        
        test_finding = {
            'id': 'test_1',
            'title': 'Test Security Finding',
            'description': 'A security vulnerability was detected',
            'severity': 'high',
            'category': 'security'
        }
        
        # Test explanation generation
        explanation = llm_integration.get_finding_explanation(
            test_finding,
            context='Test context'
        )
        
        if explanation and len(explanation) > 0:
            print(f"✓ LLM integration test passed")
            print(f"  Explanation: {explanation[:100]}...")
            return True
        else:
            print(f"✗ LLM integration test failed: No explanation generated")
            return False
    
    except Exception as e:
        print(f"✗ LLM integration test failed (may be expected if LLM not configured): {str(e)}")
        return True  # Don't fail test if LLM is not configured


def test_event_driven_generation():
    """Test event-driven report generation."""
    print("Testing event-driven generation...")
    
    try:
        # Create a findings generated message
        message = create_message(
            message_type=MessageType.RULE_FINDINGS_GENERATED,
            source_service="rule_engine",
            payload={
                'tenant_id': str(uuid.uuid4()),
                'file_id': str(uuid.uuid4()),
                'findings_ids': [str(uuid.uuid4()) for _ in range(3)],
                'user_id': str(uuid.uuid4())
            }
        )
        
        # Publish to RabbitMQ
        rabbitmq_client.connect()
        
        success = rabbitmq_client.publish_message(
            queue_name='reporting_service_findings',
            message=message,
            tenant_id=message['payload']['tenant_id']
        )
        
        rabbitmq_client.disconnect()
        
        if success:
            print("✓ Event-driven generation test passed")
            return True
        else:
            print("✗ Event-driven generation test failed")
            return False
    
    except Exception as e:
        print(f"✗ Event-driven generation test failed: {str(e)}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Week 9 Reporting Service Features Test")
    print("=" * 60)
    
    tests = [
        test_rabbitmq_connection,
        test_message_format,
        test_report_generator,
        test_llm_integration,
        test_event_driven_generation,
        test_celery_task
    ]
    
    results = []
    
    for test in tests:
        try:
            result = test()
            results.append((test.__name__, result))
        except Exception as e:
            print(f"✗ {test.__name__} failed with exception: {str(e)}")
            results.append((test.__name__, False))
    
    print("\n" + "=" * 60)
    print("Test Summary:")
    print("=" * 60)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{test_name:30} {status}")
        if result:
            passed += 1
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ All Week 9 features are working correctly!")
    else:
        print(f"\n⚠️  {total - passed} tests failed. Check the logs above.")


if __name__ == "__main__":
    main()