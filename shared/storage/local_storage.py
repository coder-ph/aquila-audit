import json
import pickle
from pathlib import Path
from typing import Any, Optional, Union
from uuid import UUID
import shutil

from shared.utils.config import settings
from shared.utils.logging import logger


class LocalStorage:
    """Local storage for non-database data."""
    
    def __init__(self):
        self.base_dir = Path(settings.data_dir) if hasattr(settings, 'data_dir') else Path("data")
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Ensure all storage directories exist."""
        directories = [
            self.base_dir / "cache",
            self.base_dir / "temp",
            self.base_dir / "backups",
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def get_cache_path(self, key: str) -> Path:
        """
        Get path for cache file.
        
        Args:
            key: Cache key
        
        Returns:
            Path to cache file
        """
        # Create safe filename from key
        import hashlib
        hash_key = hashlib.md5(key.encode()).hexdigest()
        return self.base_dir / "cache" / f"{hash_key}.cache"
    
    def cache_set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set cache value.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (not implemented for file cache)
        
        Returns:
            True if successful
        """
        try:
            cache_file = self.get_cache_path(key)
            
            # Serialize value
            if isinstance(value, (dict, list, str, int, float, bool, type(None))):
                # JSON serializable
                with open(cache_file, 'w') as f:
                    json.dump({"data": value}, f)
            else:
                # Use pickle for complex objects
                with open(cache_file, 'wb') as f:
                    pickle.dump(value, f)
            
            return True
        
        except Exception as e:
            logger.error(f"Cache set error: {str(e)}")
            return False
    
    def cache_get(self, key: str) -> Optional[Any]:
        """
        Get cached value.
        
        Args:
            key: Cache key
        
        Returns:
            Cached value or None
        """
        try:
            cache_file = self.get_cache_path(key)
            
            if not cache_file.exists():
                return None
            
            # Try JSON first
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    return data.get("data")
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Fall back to pickle
                with open(cache_file, 'rb') as f:
                    return pickle.load(f)
        
        except Exception as e:
            logger.error(f"Cache get error: {str(e)}")
            return None
    
    def cache_delete(self, key: str) -> bool:
        """
        Delete cache entry.
        
        Args:
            key: Cache key
        
        Returns:
            True if deleted
        """
        cache_file = self.get_cache_path(key)
        
        if cache_file.exists():
            cache_file.unlink()
            return True
        
        return False
    
    def create_temp_file(
        self,
        content: Union[str, bytes],
        extension: str = ".tmp"
    ) -> Path:
        """
        Create temporary file.
        
        Args:
            content: File content
            extension: File extension
        
        Returns:
            Path to temporary file
        """
        import tempfile
        import uuid
        
        temp_dir = self.base_dir / "temp"
        temp_dir.mkdir(exist_ok=True)
        
        temp_filename = f"{uuid.uuid4().hex}{extension}"
        temp_path = temp_dir / temp_filename
        
        if isinstance(content, str):
            temp_path.write_text(content, encoding='utf-8')
        else:
            temp_path.write_bytes(content)
        
        return temp_path
    
    def cleanup_temp_files(self, older_than_hours: int = 24) -> int:
        """
        Clean up old temporary files.
        
        Args:
            older_than_hours: Delete files older than this many hours
        
        Returns:
            Number of files deleted
        """
        import time
        temp_dir = self.base_dir / "temp"
        
        if not temp_dir.exists():
            return 0
        
        deleted_count = 0
        current_time = time.time()
        cutoff = older_than_hours * 3600
        
        for file_path in temp_dir.iterdir():
            if file_path.is_file():
                file_age = current_time - file_path.stat().st_mtime
                if file_age > cutoff:
                    try:
                        file_path.unlink()
                        deleted_count += 1
                    except Exception as e:
                        logger.warning(f"Could not delete temp file {file_path}: {str(e)}")
        
        return deleted_count
    
    def create_backup(
        self,
        source_path: Path,
        backup_name: Optional[str] = None
    ) -> Path:
        """
        Create backup of file or directory.
        
        Args:
            source_path: Path to file or directory to backup
            backup_name: Optional backup name
        
        Returns:
            Path to backup
        """
        if not source_path.exists():
            raise FileNotFoundError(f"Source not found: {source_path}")
        
        backup_dir = self.base_dir / "backups"
        backup_dir.mkdir(exist_ok=True)
        
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if backup_name:
            backup_filename = f"{backup_name}_{timestamp}"
        else:
            backup_filename = f"{source_path.name}_{timestamp}"
        
        backup_path = backup_dir / backup_filename
        
        if source_path.is_file():
            shutil.copy2(source_path, backup_path)
        else:
            shutil.copytree(source_path, backup_path)
        
        logger.info(f"Backup created: {backup_path}")
        return backup_path
    
    def get_storage_usage(self) -> dict:
        """
        Get storage usage statistics.
        
        Returns:
            Dictionary with storage usage information
        """
        usage = {
            "total": 0,
            "cache": 0,
            "temp": 0,
            "backups": 0,
            "uploads": 0,
            "processed": 0,
            "reports": 0
        }
        
        # Helper function to calculate directory size
        def get_dir_size(path: Path) -> int:
            total = 0
            if path.exists():
                for item in path.rglob("*"):
                    if item.is_file():
                        total += item.stat().st_size
            return total
        
        # Calculate sizes
        usage["cache"] = get_dir_size(self.base_dir / "cache")
        usage["temp"] = get_dir_size(self.base_dir / "temp")
        usage["backups"] = get_dir_size(self.base_dir / "backups")
        
        # Calculate service directories if they exist
        if hasattr(settings, 'uploads_dir'):
            usage["uploads"] = get_dir_size(Path(settings.uploads_dir))
        
        if hasattr(settings, 'processed_dir'):
            usage["processed"] = get_dir_size(Path(settings.processed_dir))
        
        if hasattr(settings, 'reports_dir'):
            usage["reports"] = get_dir_size(Path(settings.reports_dir))
        
        # Calculate total
        usage["total"] = sum(usage.values())
        
        # Convert to human readable format
        def format_size(bytes_size: int) -> str:
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if bytes_size < 1024.0:
                    return f"{bytes_size:.2f} {unit}"
                bytes_size /= 1024.0
            return f"{bytes_size:.2f} PB"
        
        usage["formatted"] = {
            key: format_size(value)
            for key, value in usage.items()
            if key != "formatted"
        }
        
        return usage


# Global local storage instance
local_storage = LocalStorage()