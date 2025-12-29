from typing import List
from pydantic_settings import BaseSettings


class RuleEngineConfig(BaseSettings):
    """Rule Engine configuration."""
    
    # Service settings
    api_title: str = "Aquila Rule Engine"
    api_description: str = "Rule evaluation engine for Aquila Audit platform"
    api_version: str = "1.0.0"
    api_docs_url: str = "/docs"
    api_redoc_url: str = "/redoc"
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8002
    debug: bool = False
    
    # Health check
    health_check_path: str = "/health"
    
    # Versioning
    api_prefix: str = "/api/v1/rules"
    
    # CORS
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ]
    
    # Rule evaluation
    max_rows_per_evaluation: int = 100000
    batch_size: int = 1000
    evaluation_timeout: int = 300  # 5 minutes
    
    # Cache
    cache_rules: bool = True
    cache_ttl: int = 300  # 5 minutes
    
    class Config:
        env_file = ".env"
        env_prefix = "RULE_ENGINE_"


# Global config instance
config = RuleEngineConfig()