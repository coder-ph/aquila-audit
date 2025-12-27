import os
import shutil
from pathlib import Path
from typing import Optional, BinaryIO, Union
from uuid import UUID
import magic
from fastapi import UploadFile

from shared.utils.config import settings
from shared.utils.logging import logger


class FileManager:
    """Manager for file operations with tenant isolation."""
    
    def __init__(self):
        self.uploads_dir = Path(settings.uploads_dir)
        self.processed_dir = Path(settings.processed_dir)
        self.reports_dir = Path(settings.reports_dir)
        self.allowed_extensions = settings.allowed_extensions
        
        # Ensure directories exist
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Ensure all required directories exist."""
        directories = [
            self.uploads_dir,
            self.processed_dir,
            self.reports_dir,
            Path(settings.models_dir),
            Path(settings.logs_dir)
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def get_tenant_directory(
        self,
        base_dir: Path,
        tenant_id: UUID,
        create: bool = True
    ) -> Path:
        """
        Get directory path for specific tenant.
        
        Args:
            base_dir: Base directory
            tenant_id: Tenant ID
            create: Create directory if it doesn't exist
        
        Returns:
            Tenant directory path
        """
        tenant_dir = base_dir / str(tenant_id)
        
        if create and not tenant_dir.exists():
            tenant_dir.mkdir(parents=True, exist_ok=True)
        
        return tenant_dir
    
    def validate_file(
        self,
        file: UploadFile,
        max_size: Optional[int] = None
    ) -> tuple[bool, str]:
        """
        Validate uploaded file.
        
        Args:
            file: Uploaded file
            max_size: Maximum file size in bytes
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if max_size is None:
            max_size = settings.max_upload_size
        
        # Check file extension
        file_extension = Path(file.filename).suffix.lower()
        if file_extension not in self.allowed_extensions:
            return False, f"File type not allowed. Allowed types: {', '.join(self.allowed_extensions)}"
        
        # Check file size
        try:
            # Read file size
            file.file.seek(0, 2)  # Seek to end
            file_size = file.file.tell()
            file.file.seek(0)  # Reset to beginning
            
            if file_size > max_size:
                return False, f"File too large. Maximum size: {max_size / 1024 / 1024:.1f}MB"
            
            if file_size == 0:
                return False, "File is empty"
        
        except Exception as e:
            logger.error(f"Error checking file size: {str(e)}")
            return False, "Error reading file"
        
        # Validate file content using magic
        try:
            mime = magic.Magic(mime=True)
            content = file.file.read(1024)
            file.file.seek(0)
            
            mime_type = mime.from_buffer(content)
            
            # Map extensions to MIME types
            mime_mapping = {
                '.csv': 'text/csv',
                '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                '.xls': 'application/vnd.ms-excel',
                '.json': 'application/json'
            }
            
            expected_mime = mime_mapping.get(file_extension)
            if expected_mime and mime_type != expected_mime:
                return False, f"File content doesn't match extension. Expected {expected_mime}, got {mime_type}"
        
        except Exception as e:
            logger.warning(f"Could not validate MIME type: {str(e)}")
        
        return True, ""
    
    def save_uploaded_file(
        self,
        file: UploadFile,
        tenant_id: UUID,
        subdirectory: Optional[str] = None
    ) -> Path:
        """
        Save uploaded file with tenant isolation.
        
        Args:
            file: Uploaded file
            tenant_id: Tenant ID
            subdirectory: Optional subdirectory within tenant directory
        
        Returns:
            Path to saved file
        """
        # Get tenant directory
        tenant_dir = self.get_tenant_directory(self.uploads_dir, tenant_id)
        
        # Add subdirectory if specified
        if subdirectory:
            save_dir = tenant_dir / subdirectory
            save_dir.mkdir(parents=True, exist_ok=True)
        else:
            save_dir = tenant_dir
        
        # Generate unique filename
        original_filename = Path(file.filename)
        unique_filename = self._generate_unique_filename(save_dir, original_filename)
        file_path = save_dir / unique_filename
        
        try:
            # Save file
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            logger.info(f"File saved: {file_path}", tenant_id=str(tenant_id))
            return file_path
        
        except Exception as e:
            logger.error(f"Error saving file: {str(e)}", tenant_id=str(tenant_id))
            raise
    
    def _generate_unique_filename(
        self,
        directory: Path,
        original_filename: Path
    ) -> str:
        """
        Generate unique filename to avoid collisions.
        
        Args:
            directory: Target directory
            original_filename: Original filename
        
        Returns:
            Unique filename
        """
        import uuid
        import time
        
        stem = original_filename.stem
        extension = original_filename.suffix
        
        # Create filename with timestamp and UUID
        timestamp = int(time.time())
        unique_id = uuid.uuid4().hex[:8]
        
        unique_name = f"{stem}_{timestamp}_{unique_id}{extension}"
        
        # Check if file already exists (unlikely but possible)
        counter = 1
        while (directory / unique_name).exists():
            unique_name = f"{stem}_{timestamp}_{unique_id}_{counter}{extension}"
            counter += 1
        
        return unique_name
    
    def get_file_path(
        self,
        tenant_id: UUID,
        filename: str,
        file_type: str = "upload"
    ) -> Optional[Path]:
        """
        Get path to a file.
        
        Args:
            tenant_id: Tenant ID
            filename: Filename
            file_type: Type of file (upload, processed, report)
        
        Returns:
            Path to file or None
        """
        if file_type == "upload":
            base_dir = self.uploads_dir
        elif file_type == "processed":
            base_dir = self.processed_dir
        elif file_type == "report":
            base_dir = self.reports_dir
        else:
            logger.error(f"Unknown file type: {file_type}")
            return None
        
        tenant_dir = self.get_tenant_directory(base_dir, tenant_id, create=False)
        file_path = tenant_dir / filename
        
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return None
        
        return file_path
    
    def delete_file(
        self,
        tenant_id: UUID,
        filename: str,
        file_type: str = "upload"
    ) -> bool:
        """
        Delete a file.
        
        Args:
            tenant_id: Tenant ID
            filename: Filename
            file_type: Type of file
        
        Returns:
            True if deleted successfully
        """
        file_path = self.get_file_path(tenant_id, filename, file_type)
        
        if not file_path:
            return False
        
        try:
            file_path.unlink()
            logger.info(f"File deleted: {file_path}", tenant_id=str(tenant_id))
            return True
        
        except Exception as e:
            logger.error(f"Error deleting file: {str(e)}", tenant_id=str(tenant_id))
            return False
    
    def list_files(
        self,
        tenant_id: UUID,
        file_type: str = "upload",
        pattern: str = "*"
    ) -> list[dict]:
        """
        List files in tenant directory.
        
        Args:
            tenant_id: Tenant ID
            file_type: Type of files
            pattern: Filename pattern
        
        Returns:
            List of file information dictionaries
        """
        if file_type == "upload":
            base_dir = self.uploads_dir
        elif file_type == "processed":
            base_dir = self.processed_dir
        elif file_type == "report":
            base_dir = self.reports_dir
        else:
            return []
        
        tenant_dir = self.get_tenant_directory(base_dir, tenant_id, create=False)
        
        if not tenant_dir.exists():
            return []
        
        files = []
        for file_path in tenant_dir.glob(pattern):
            if file_path.is_file():
                stat = file_path.stat()
                files.append({
                    "filename": file_path.name,
                    "path": str(file_path),
                    "size": stat.st_size,
                    "created_at": stat.st_ctime,
                    "modified_at": stat.st_mtime
                })
        
        return files
    
    def get_file_size(self, file_path: Path) -> int:
        """
        Get file size in bytes.
        
        Args:
            file_path: Path to file
        
        Returns:
            File size in bytes
        """
        return file_path.stat().st_size
    
    def move_file(
        self,
        source_path: Path,
        target_dir: Path,
        new_filename: Optional[str] = None
    ) -> Path:
        """
        Move file to new location.
        
        Args:
            source_path: Source file path
            target_dir: Target directory
            new_filename: New filename (optional)
        
        Returns:
            New file path
        """
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")
        
        target_dir.mkdir(parents=True, exist_ok=True)
        
        if new_filename:
            target_path = target_dir / new_filename
        else:
            target_path = target_dir / source_path.name
        
        # Handle filename collisions
        counter = 1
        while target_path.exists():
            name = target_path.stem
            extension = target_path.suffix
            target_path = target_dir / f"{name}_{counter}{extension}"
            counter += 1
        
        shutil.move(str(source_path), str(target_path))
        return target_path


# Global file manager instance
file_manager = FileManager()