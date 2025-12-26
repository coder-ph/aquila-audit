from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import PostgresDsn, RedisDsn, AmqpDsn, validator


class Settings(BaseSettings):
    """Application settings."""
    
    # Application
    app_name: str = "Aquila Audit"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    
    # API
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000"]
    
    # Database
    database_url: PostgresDsn = "postgresql://aquila:aquila123@postgres:5432/aquila_audit"
    database_pool_size: int = 20
    database_max_overflow: int = 40
    
    # Redis
    redis_url: RedisDsn = "redis://localhost:6379/0"
    redis_cache_ttl: int = 300  # 5 minutes
    
    # RabbitMQ
    rabbitmq_url: AmqpDsn = "amqp://aquila:aquila123@localhost:5672"
    
    # Celery
    celery_broker_url: str = "amqp://aquila:aquila123@localhost:5672"
    celery_result_backend: str = "redis://localhost:6379/0"
    
    # JWT
    secret_key: str = "qzeasytrb62!221"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # File Upload
    max_upload_size: int = 104_857_600  # 100MB
    allowed_extensions: list[str] = [".csv", ".xlsx", ".xls", ".json"]
    
    # Storage Paths
    uploads_dir: str = "data/uploads/tenants"
    processed_dir: str = "data/processed/tenants"
    reports_dir: str = "data/reports/tenants"
    models_dir: str = "data/models/ml_models"
    logs_dir: str = "data/logs"
    
    @validator("cors_origins", pre=True)
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @validator("allowed_extensions", pre=True)
    def parse_allowed_extensions(cls, v):
        if isinstance(v, str):
            return [ext.strip() for ext in v.split(",")]
        return v
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()