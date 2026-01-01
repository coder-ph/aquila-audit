"""
Celery tasks for the worker service.
"""
from services.worker_service.tasks.file_processing import (
    process_uploaded_file,
    cleanup_temp_files,
    validate_file_structure
)

from services.worker_service.tasks.rule_evaluation import (
    evaluate_rules_for_file,
    cleanup_old_results,
    bulk_evaluate_rules
)

from services.worker_service.tasks.report_generation import (
    generate_report_task,
    generate_batch_reports_task,
    cleanup_generated_reports
)

__all__ = [
    # File processing tasks
    'process_uploaded_file',
    'cleanup_temp_files',
    'validate_file_structure',
    
    # Rule evaluation tasks
    'evaluate_rules_for_file',
    'cleanup_old_results',
    'bulk_evaluate_rules',
    
    # Report generation tasks
    'generate_report_task',
    'generate_batch_reports_task',
    'cleanup_generated_reports'
]