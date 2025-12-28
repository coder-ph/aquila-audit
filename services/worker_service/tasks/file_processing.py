import pandas as pd
from celery import shared_task
from sqlalchemy.orm import Session
from uuid import UUID
import json
from datetime import datetime
from pathlib import Path

from shared.database.session import get_session
from shared.models.file_models import File, FileStatus
from shared.models.finding_models import Finding
from shared.messaging.event_publisher import event_publisher
from shared.utils.logging import logger


@shared_task(bind=True, max_retries=3)
def process_file_task(self, file_id: str, tenant_id: str):
    """
    Process an uploaded file.
    
    Args:
        file_id: File ID
        tenant_id: Tenant ID
    """
    file_uuid = UUID(file_id)
    tenant_uuid = UUID(tenant_id)
    
    logger.info(f"Processing file: {file_id}", tenant_id=tenant_id)
    
    with get_session() as db:
        # Get file
        db_file = db.query(File).filter(
            File.id == file_uuid,
            File.tenant_id == tenant_uuid
        ).first()
        
        if not db_file:
            logger.error(f"File not found: {file_id}", tenant_id=tenant_id)
            raise ValueError(f"File not found: {file_id}")
        
        try:
            # Update status
            db_file.status = FileStatus.PROCESSING
            db_file.processing_started_at = datetime.utcnow()
            db.commit()
            
            # Process file based on type
            if db_file.file_type == ".csv":
                result = process_csv_file(db_file, db)
            elif db_file.file_type in [".xlsx", ".xls"]:
                result = process_excel_file(db_file, db)
            elif db_file.file_type == ".json":
                result = process_json_file(db_file, db)
            else:
                raise ValueError(f"Unsupported file type: {db_file.file_type}")
            
            # Update file with results
            db_file.status = FileStatus.PROCESSED
            db_file.processing_completed_at = datetime.utcnow()
            db_file.processing_result = result
            db.commit()
            
            logger.info(f"File processed successfully: {file_id}", tenant_id=tenant_id)
            
            # Publish file processed event
            event_publisher.publish(
                queue_name="rule_evaluation",
                message_type="file.processed",
                source_service="worker_service",
                payload={
                    "tenant_id": tenant_id,
                    "file_id": file_id,
                    "data_path": db_file.storage_path,
                    "processing_result": result
                },
                tenant_id=tenant_uuid
            )
            
            return {
                "status": "success",
                "file_id": file_id,
                "processing_result": result
            }
            
        except Exception as e:
            # Update file with error
            db_file.status = FileStatus.FAILED
            db_file.error_message = str(e)
            db_file.processing_completed_at = datetime.utcnow()
            db.commit()
            
            logger.error(f"Failed to process file: {str(e)}", tenant_id=tenant_id)
            
            # Retry the task
            raise self.retry(exc=e, countdown=60)


def process_csv_file(db_file: File, db: Session) -> dict:
    """Process CSV file."""
    file_path = Path(db_file.storage_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    # Read CSV file
    try:
        df = pd.read_csv(file_path)
        
        # Basic validation
        if df.empty:
            raise ValueError("CSV file is empty")
        
        # Extract metadata
        metadata = {
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": list(df.columns),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "sample_data": df.head().to_dict(orient="records")
        }
        
        # Update file metadata
        db_file.metadata = metadata
        db.commit()
        
        return {
            "file_type": "csv",
            "rows_processed": len(df),
            "columns_processed": len(df.columns),
            "metadata": metadata
        }
        
    except Exception as e:
        logger.error(f"Error processing CSV file: {str(e)}")
        raise


def process_excel_file(db_file: File, db: Session) -> dict:
    """Process Excel file."""
    file_path = Path(db_file.storage_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    try:
        # Read Excel file
        excel_file = pd.ExcelFile(file_path)
        
        # Process each sheet
        sheet_results = {}
        total_rows = 0
        
        for sheet_name in excel_file.sheet_names:
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
            
            if df.empty:
                continue
            
            sheet_results[sheet_name] = {
                "row_count": len(df),
                "column_count": len(df.columns),
                "columns": list(df.columns),
                "sample_data": df.head().to_dict(orient="records")
            }
            
            total_rows += len(df)
        
        # Update file metadata
        metadata = {
            "sheets": list(excel_file.sheet_names),
            "sheet_results": sheet_results,
            "total_rows": total_rows
        }
        
        db_file.metadata = metadata
        db.commit()
        
        return {
            "file_type": "excel",
            "sheets_processed": len(excel_file.sheet_names),
            "total_rows_processed": total_rows,
            "metadata": metadata
        }
        
    except Exception as e:
        logger.error(f"Error processing Excel file: {str(e)}")
        raise


def process_json_file(db_file: File, db: Session) -> dict:
    """Process JSON file."""
    file_path = Path(db_file.storage_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    try:
        # Read JSON file
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        # Determine if it's a list or object
        if isinstance(data, list):
            row_count = len(data)
            if data and isinstance(data[0], dict):
                columns = list(data[0].keys()) if data else []
            else:
                columns = ["value"]
            sample_data = data[:5] if data else []
        else:
            row_count = 1
            columns = list(data.keys()) if isinstance(data, dict) else ["value"]
            sample_data = [data] if data else []
        
        # Update file metadata
        metadata = {
            "row_count": row_count,
            "column_count": len(columns),
            "columns": columns,
            "sample_data": sample_data
        }
        
        db_file.metadata = metadata
        db.commit()
        
        return {
            "file_type": "json",
            "rows_processed": row_count,
            "columns_processed": len(columns),
            "metadata": metadata
        }
        
    except Exception as e:
        logger.error(f"Error processing JSON file: {str(e)}")
        raise


@shared_task
def cleanup_temp_files():
    """Clean up temporary files."""
    from shared.storage.local_storage import local_storage
    
    deleted_count = local_storage.cleanup_temp_files(older_than_hours=24)
    
    logger.info(f"Cleaned up {deleted_count} temporary files")
    
    return {"deleted_count": deleted_count}