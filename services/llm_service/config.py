from typing import List, Optional
from pydantic import BaseSettings


class LLMServiceConfig(BaseSettings):
    """LLM Service configuration."""
    
    # Service settings
    api_title: str = "Aquila LLM Service"
    api_description: str = "AI-powered explanations and analysis for Aquila Audit"
    api_version: str = "1.0.0"
    api_docs_url: str = "/docs"
    api_redoc_url: str = "/redoc"
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8004
    debug: bool = False
    
    # Health check
    health_check_path: str = "/health"
    
    # Versioning
    api_prefix: str = "/api/v1/llm"
    
    # CORS
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ]
    
    # OpenAI Configuration
    openai_api_key: Optional[str] = None
    openai_organization: Optional[str] = None
    openai_base_url: Optional[str] = None
    
    # Model settings
    default_model: str = "gpt-4"  # gpt-4, gpt-3.5-turbo
    fallback_model: str = "gpt-3.5-turbo"
    max_tokens: int = 1000
    temperature: float = 0.7
    timeout: int = 30  # seconds
    
    # Budget and Cost Management
    default_monthly_budget: float = 100.0  # USD
    cost_warning_threshold: float = 0.8  # 80% of budget
    cost_limit_threshold: float = 0.95  # 95% of budget
    
    # Cache settings
    cache_enabled: bool = True
    cache_ttl: int = 86400  # 24 hours in seconds
    cache_max_size: int = 1000
    
    # PII Redaction
    pii_redaction_enabled: bool = True
    pii_entities: List[str] = [
        "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD",
        "SSN", "PERSON", "LOCATION"
    ]
    
    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_period: int = 60  # seconds
    
    class Config:
        env_file = ".env"
        env_prefix = "LLM_SERVICE_"


# Global config instance
config = LLMServiceConfig()