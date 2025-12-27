from typing import List
from pydantic import BaseSettings


class APIGatewayConfig(BaseSettings):
    """API Gateway configuration."""
    
    # API Gateway specific settings
    api_title: str = "Aquila Audit API"
    api_description: str = "Audit compliance and anomaly detection platform"
    api_version: str = "1.0.0"
    api_docs_url: str = "/docs"
    api_redoc_url: str = "/redoc"
    
    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_period: int = 60  # seconds
    
    # Request timeout
    request_timeout: int = 30  # seconds
    
    # Health check
    health_check_path: str = "/health"
    
    # Versioning
    api_prefix: str = "/api/v1"
    
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
    enable_https_redirect: bool = False
    
    class Config:
        env_file = ".env"
        env_prefix = "API_GATEWAY_"


# Global config instance
config = APIGatewayConfig()