from typing import List
from pydantic_settings import BaseSettings


class MLServiceConfig(BaseSettings):
    """ML Service configuration."""
    
    # Service settings
    api_title: str = "Aquila ML Service"
    api_description: str = "Machine learning and anomaly detection for Aquila Audit"
    api_version: str = "1.0.0"
    api_docs_url: str = "/docs"
    api_redoc_url: str = "/redoc"
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8003
    debug: bool = False
    
    # Health check
    health_check_path: str = "/health"
    
    # Versioning
    api_prefix: str = "/api/v1/ml"
    
    # CORS
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ]
    
    # ML Model settings
    models_dir: str = "data/models/ml_models"
    default_model: str = "isolation_forest_v1"
    
    # Isolation Forest settings
    isolation_forest_contamination: float = 0.1
    isolation_forest_n_estimators: int = 100
    isolation_forest_max_samples: float = 0.8
    
    # Feature extraction
    max_features: int = 50
    feature_scaling: bool = True
    categorical_encoding: str = "onehot"  # onehot, label, target
    
    # Training settings
    min_samples_train: int = 1000
    test_size: float = 0.2
    random_state: int = 42
    
    # Shadow mode
    shadow_mode_enabled: bool = True
    shadow_mode_threshold: float = 0.7
    
    class Config:
        env_file = ".env"
        env_prefix = "ML_SERVICE_"


# Global config instance
config = MLServiceConfig()