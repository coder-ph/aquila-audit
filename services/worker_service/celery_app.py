from celery import Celery
from celery.schedules import crontab

from shared.utils.config import settings
from shared.utils.logging import logger


# Create Celery app
celery_app = Celery(
    "aquila_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "services.worker_service.tasks.file_processing",
        "services.worker_service.tasks.rule_evaluation",
        "services.worker_service.tasks.report_generation",
    ]
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_max_tasks_per_child=1000,
    worker_prefetch_multiplier=1,
    
    # Beat schedule for periodic tasks
    beat_schedule={
        "cleanup-temp-files": {
            "task": "services.worker_service.tasks.file_processing.cleanup_temp_files",
            "schedule": crontab(hour=2, minute=0),  # Daily at 2 AM
        },
        "cleanup-old-results": {
            "task": "services.worker_service.tasks.rule_evaluation.cleanup_old_results",
            "schedule": crontab(hour=3, minute=0),  # Daily at 3 AM
        },
    }
)

# Configure task routes
celery_app.conf.task_routes = {
    "services.worker_service.tasks.file_processing.*": {
        "queue": "file_processing"
    },
    "services.worker_service.tasks.rule_evaluation.*": {
        "queue": "rule_evaluation"
    },
    "services.worker_service.tasks.report_generation.*": {
        "queue": "report_generation"
    },
}

logger.info("Celery app configured")


@celery_app.task(bind=True)
def debug_task(self):
    """Debug task to test Celery."""
    logger.info(f"Debug task executed: {self.request.id}")
    return {"status": "success", "task_id": self.request.id}