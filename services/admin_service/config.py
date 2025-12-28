from typing import List
from pydantic import BaseSettings


class AdminServiceConfig(BaseSettings):
    """Admin Service configuration."""
    
    # Service settings
    api_title: str = "Aquila Admin Service"
    api_description: str = "Admin management for Aquila Audit platform"
    api_version: str = "1.0.0"
    api_docs_url: str = "/docs"
    api_redoc_url: str = "/redoc"
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8001
    debug: bool = False
    
    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_period: int = 60
    
    # Request timeout
    request_timeout: int = 30
    
    # Health check
    health_check_path: str = "/health"
    
    # Versioning
    api_prefix: str = "/api/v1/admin"
    
    # CORS
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ]
    
    # Logging
    log_format: str = "json"
    access_log_enabled: bool = True
    
    # Security
    enable_rate_limiting: bool = True
    enable_cors: bool = True
    require_admin_token: bool = True
    admin_token: str = "admin-secret-token-change-in-production"
    
    class Config:
        env_file = ".env"
        env_prefix = "ADMIN_SERVICE_"


# Global config instance
config = AdminServiceConfig()