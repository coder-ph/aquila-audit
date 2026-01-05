"""
Billing Service configuration.
"""
from typing import List
from pydantic_settings import BaseSettings


class BillingServiceConfig(BaseSettings):
    """Billing Service configuration."""
    
    # Service settings
    api_title: str = "Aquila Billing Service"
    api_description: str = "Usage tracking and billing for Aquila Audit platform"
    api_version: str = "1.0.0"
    api_docs_url: str = "/docs"
    api_redoc_url: str = "/redoc"
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8002
    debug: bool = False
    
    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_period: int = 60
    
    # Request timeout
    request_timeout: int = 30
    
    # Health check
    health_check_path: str = "/health"
    
    # Versioning
    api_prefix: str = "/api/v1/billing"
    
    # CORS
    enable_cors: bool = True
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://localhost:8001",  # Admin service
    ]
    
    # Logging
    log_format: str = "json"
    access_log_enabled: bool = True
    
    # Usage tracking
    usage_aggregation_interval: int = 300  # 5 minutes in seconds
    usage_retention_days: int = 90
    
    # Cost calculation
    cost_per_storage_gb: float = 0.10  # $0.10 per GB per month
    cost_per_file_upload: float = 0.001  # $0.001 per file
    cost_per_api_call: float = 0.0001  # $0.0001 per API call
    cost_per_ai_token: float = 0.000002  # $0.000002 per AI token
    
    # Budget alerts
    budget_warning_threshold: float = 0.8  # 80% of budget
    budget_critical_threshold: float = 0.95  # 95% of budget
    
    # Email notifications
    email_enabled: bool = False
    email_from: str = "billing@aquila-audit.com"
    email_smtp_host: str = "smtp.gmail.com"
    email_smtp_port: int = 587
    
    # Stripe integration (optional)
    stripe_enabled: bool = False
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    
    class Config:
        env_file = ".env"
        env_prefix = "BILLING_SERVICE_"


# Global config instance
config = BillingServiceConfig()