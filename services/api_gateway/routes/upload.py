from typing import List, Optional
from fastapi import (
    APIRouter, 
    Depends, 
    HTTPException, 
    status, 
    UploadFile, 
    File, 
    Form,
    BackgroundTasks
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from uuid import UUID
import os

from shared.database.session import get_session
from shared.storage.file_manager import file_manager
from shared.messaging.event_publisher import event_publisher
from shared.utils.logging import logger

from services.api_gateway.dependencies.auth import (
    get_current_user, 
    get_current_user_with_tenant
)
from shared.models.schemas import FileResponse as FileResponseSchema, PaginatedResponse
from shared.models.file_models import File as FileModel

# Create router
router = APIRouter()


@router.post("/", response_model=FileResponseSchema, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session),
    background_tasks: BackgroundTasks = None
):
    """
    Upload a file for processing.
    
    Supported file types: CSV, Excel, JSON
    Maximum file size: 100MB
    """
    user_id, tenant_id = user_info
    
    # Validate file
    is_valid, error_message = file_manager.validate_file(file)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message
        )
    
    # Save file to storage
    try:
        file_path = file_manager.save_uploaded_file(file, tenant_id)
    except Exception as e:
        logger.error(f"Failed to save file: {str(e)}", tenant_id=str(tenant_id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save file"
        )
    
    # Create file record in database
    try:
        db_file = FileModel(
            tenant_id=tenant_id,
            filename=file_path.name,
            original_filename=file.filename,
            file_type=file_path.suffix.lower(),
            file_size=file_manager.get_file_size(file_path),
            storage_path=str(file_path),
            uploaded_by=user_id,
            metadata={
                "description": description,
                "tags": tags.split(",") if tags else [],
                "content_type": file.content_type
            }
        )
        
        db.add(db_file)
        db.commit()
        db.refresh(db_file)
        
    except Exception as e:
        # Clean up uploaded file if database operation fails
        file_manager.delete_file(tenant_id, file_path.name)
        logger.error(f"Failed to create file record: {str(e)}", tenant_id=str(tenant_id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create file record"
        )
    
    # Publish file uploaded event (async)
    if background_tasks:
        background_tasks.add_task(
            event_publisher.publish_file_uploaded,
            tenant_id=tenant_id,
            file_id=db_file.id,
            filename=file.filename,
            file_path=str(file_path),
            file_size=db_file.file_size,
            file_type=db_file.file_type,
            uploaded_by=user_id
        )
    
    logger.info(
        f"File uploaded successfully: {file.filename}",
        file_id=str(db_file.id),
        tenant_id=str(tenant_id),
        user_id=str(user_id)
    )
    
    return db_file


@router.post("/chunked/start")
async def start_chunked_upload(
    filename: str = Form(...),
    file_size: int = Form(...),
    total_chunks: int = Form(...),
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session)
):
    """
    Start a chunked file upload.
    
    This endpoint should be called before uploading chunks.
    """
    user_id, tenant_id = user_info
    
    # Validate file size
    if file_size > file_manager.max_upload_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size: {file_manager.max_upload_size / 1024 / 1024:.1f}MB"
        )
    
    # Create initial file record
    db_file = FileModel(
        tenant_id=tenant_id,
        filename=f"temp_{UUID().hex}",  # Temporary filename
        original_filename=filename,
        file_type=os.path.splitext(filename)[1].lower(),
        file_size=file_size,
        storage_path="",  # Will be updated when complete
        uploaded_by=user_id,
        status="uploading"
    )
    
    db.add(db_file)
    db.commit()
    db.refresh(db_file)
    
    return {
        "file_id": str(db_file.id),
        "chunk_size": 1024 * 1024,  # 1MB chunks
        "total_chunks": total_chunks
    }


@router.post("/chunked/{file_id}/chunk")
async def upload_chunk(
    file_id: UUID,
    chunk_number: int = Form(...),
    chunk_data: str = Form(...),  # Base64 encoded
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session)
):
    """
    Upload a chunk of a file.
    """
    user_id, tenant_id = user_info
    
    # Get file
    db_file = db.query(FileModel).filter(
        FileModel.id == file_id,
        FileModel.tenant_id == tenant_id
    ).first()
    
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    # Here you would save the chunk to temporary storage
    # For now, we'll just acknowledge receipt
    
    return {
        "chunk_number": chunk_number,
        "received": True
    }


@router.post("/chunked/{file_id}/complete")
async def complete_chunked_upload(
    file_id: UUID,
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session),
    background_tasks: BackgroundTasks = None
):
    """
    Complete a chunked file upload.
    
    This endpoint should be called after all chunks are uploaded.
    """
    user_id, tenant_id = user_info
    
    # Get file
    db_file = db.query(FileModel).filter(
        FileModel.id == file_id,
        FileModel.tenant_id == tenant_id
    ).first()
    
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    # Here you would:
    # 1. Combine all chunks into the final file
    # 2. Validate the complete file
    # 3. Move to permanent storage
    # 4. Update file record
    
    # For now, we'll simulate completion
    db_file.status = "uploaded"
    db.commit()
    
    # Publish file uploaded event
    if background_tasks:
        background_tasks.add_task(
            event_publisher.publish_file_uploaded,
            tenant_id=tenant_id,
            file_id=db_file.id,
            filename=db_file.original_filename,
            file_path=db_file.storage_path,
            file_size=db_file.file_size,
            file_type=db_file.file_type,
            uploaded_by=user_id
        )
    
    return {"message": "File upload completed", "file_id": str(file_id)}


@router.get("/", response_model=PaginatedResponse)
async def list_files(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    file_type: Optional[str] = None,
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session)
):
    """
    List uploaded files.
    """
    user_id, tenant_id = user_info
    
    # Build query
    query = db.query(FileModel).filter(FileModel.tenant_id == tenant_id)
    
    # Apply filters
    if status:
        query = query.filter(FileModel.status == status)
    
    if file_type:
        query = query.filter(FileModel.file_type == file_type)
    
    # Get total count
    total = query.count()
    
    # Get paginated results
    files = query.order_by(FileModel.created_at.desc()).offset(skip).limit(limit).all()
    
    return {
        "items": files,
        "total": total,
        "page": skip // limit + 1,
        "page_size": limit,
        "total_pages": (total + limit - 1) // limit
    }


@router.get("/{file_id}", response_model=FileResponseSchema)
async def get_file(
    file_id: UUID,
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session)
):
    """
    Get file details.
    """
    user_id, tenant_id = user_info
    
    db_file = db.query(FileModel).filter(
        FileModel.id == file_id,
        FileModel.tenant_id == tenant_id
    ).first()
    
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    return db_file


@router.get("/{file_id}/download")
async def download_file(
    file_id: UUID,
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session)
):
    """
    Download a file.
    """
    user_id, tenant_id = user_info
    
    db_file = db.query(FileModel).filter(
        FileModel.id == file_id,
        FileModel.tenant_id == tenant_id
    ).first()
    
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    if db_file.status != "processed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is not available for download"
        )
    
    file_path = file_manager.get_file_path(
        tenant_id,
        db_file.filename,
        file_type="upload"
    )
    
    if not file_path or not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found in storage"
        )
    
    return FileResponse(
        path=file_path,
        filename=db_file.original_filename,
        media_type="application/octet-stream"
    )


@router.delete("/{file_id}")
async def delete_file(
    file_id: UUID,
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session)
):
    """
    Delete a file.
    """
    user_id, tenant_id = user_info
    
    db_file = db.query(FileModel).filter(
        FileModel.id == file_id,
        FileModel.tenant_id == tenant_id
    ).first()
    
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    # Delete from storage
    success = file_manager.delete_file(tenant_id, db_file.filename)
    
    if not success:
        logger.warning(
            f"File not found in storage, but deleting database record",
            file_id=str(file_id),
            tenant_id=str(tenant_id)
        )
    
    # Delete database record
    db.delete(db_file)
    db.commit()
    
    logger.info(
        f"File deleted",
        file_id=str(file_id),
        tenant_id=str(tenant_id),
        user_id=str(user_id)
    )
    
    return {"message": "File deleted successfully"}


@router.get("/{file_id}/status")
async def get_file_status(
    file_id: UUID,
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session)
):
    """
    Get file processing status.
    """
    user_id, tenant_id = user_info
    
    db_file = db.query(FileModel).filter(
        FileModel.id == file_id,
        FileModel.tenant_id == tenant_id
    ).first()
    
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    return {
        "file_id": str(db_file.id),
        "status": db_file.status,
        "processing_started_at": db_file.processing_started_at,
        "processing_completed_at": db_file.processing_completed_at,
        "processing_duration": db_file.processing_duration,
        "error_message": db_file.error_message
    }


@router.post("/{file_id}/reprocess")
async def reprocess_file(
    file_id: UUID,
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session),
    background_tasks: BackgroundTasks = None
):
    """
    Reprocess a file.
    """
    user_id, tenant_id = user_info
    
    db_file = db.query(FileModel).filter(
        FileModel.id == file_id,
        FileModel.tenant_id == tenant_id
    ).first()
    
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    # Reset status
    db_file.status = "uploaded"
    db_file.processing_started_at = None
    db_file.processing_completed_at = None
    db_file.error_message = None
    db.commit()
    
    # Publish file uploaded event to trigger reprocessing
    if background_tasks:
        background_tasks.add_task(
            event_publisher.publish_file_uploaded,
            tenant_id=tenant_id,
            file_id=db_file.id,
            filename=db_file.original_filename,
            file_path=db_file.storage_path,
            file_size=db_file.file_size,
            file_type=db_file.file_type,
            uploaded_by=user_id
        )
    
    return {"message": "File queued for reprocessing", "file_id": str(file_id)}