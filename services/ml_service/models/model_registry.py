"""
Model registry for tracking ML models.
"""
import json
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session

from shared.database.session import get_session
from shared.models.base import BaseModel
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, Float, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from shared.utils.logging import logger
from services.ml_service.config import config


class MLModel(BaseModel):
    """ML Model registry database model."""
    
    __tablename__ = "ml_models"
    
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    model_name = Column(String(255), nullable=False)
    model_type = Column(String(100), nullable=False)  # isolation_forest, autoencoder, etc.
    model_version = Column(String(50), default="1.0.0", nullable=False)
    
    # Model information
    description = Column(Text, nullable=True)
    feature_names = Column(JSONB, nullable=True)  # List of feature names
    model_parameters = Column(JSONB, nullable=True)  # Model hyperparameters
    
    # Training information
    training_samples = Column(Integer, nullable=True)
    trained_at = Column(DateTime, nullable=True)
    training_metrics = Column(JSONB, nullable=True)
    
    # Performance metrics
    performance_metrics = Column(JSONB, nullable=True)
    last_evaluated_at = Column(DateTime, nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_production = Column(Boolean, default=False, nullable=False)
    is_shadow = Column(Boolean, default=False, nullable=False)
    
    # Storage
    model_path = Column(String(500), nullable=True)  # Path to model file
    feature_extractor_path = Column(String(500), nullable=True)
    
    def __repr__(self):
        return f"<MLModel {self.model_name} v{self.model_version}>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        
        # Add computed properties
        data["model_age_days"] = None
        if self.trained_at:
            age = (datetime.utcnow() - self.trained_at).days
            data["model_age_days"] = age
        
        return data


class ModelRegistry:
    """Database-backed model registry."""
    
    def __init__(self):
        pass
    
    def register_model(
        self,
        db: Session,
        tenant_id: str,
        model_name: str,
        model_type: str,
        model_version: str = "1.0.0",
        description: str = "",
        feature_names: List[str] = None,
        model_parameters: Dict[str, Any] = None,
        model_path: str = None,
        feature_extractor_path: str = None,
        is_production: bool = False,
        is_shadow: bool = False
    ) -> MLModel:
        """
        Register a new model in the registry.
        
        Args:
            db: Database session
            tenant_id: Tenant ID
            model_name: Name of the model
            model_type: Type of model
            model_version: Model version
            description: Model description
            feature_names: List of feature names
            model_parameters: Model hyperparameters
            model_path: Path to model file
            feature_extractor_path: Path to feature extractor
            is_production: Whether this is a production model
            is_shadow: Whether this is a shadow model
        
        Returns:
            Registered model
        """
        # Check if model already exists
        existing = db.query(MLModel).filter(
            MLModel.tenant_id == tenant_id,
            MLModel.model_name == model_name,
            MLModel.model_version == model_version
        ).first()
        
        if existing:
            raise ValueError(f"Model '{model_name}' v{model_version} already exists")
        
        # Create model record
        model = MLModel(
            tenant_id=tenant_id,
            model_name=model_name,
            model_type=model_type,
            model_version=model_version,
            description=description,
            feature_names=feature_names or [],
            model_parameters=model_parameters or {},
            model_path=model_path,
            feature_extractor_path=feature_extractor_path,
            is_production=is_production,
            is_shadow=is_shadow
        )
        
        db.add(model)
        db.commit()
        db.refresh(model)
        
        logger.info(f"Registered model: {model_name} v{model_version}")
        
        return model
    
    def update_model_training(
        self,
        db: Session,
        model_id: str,
        training_samples: int,
        training_metrics: Dict[str, Any]
    ) -> bool:
        """
        Update model with training information.
        
        Args:
            db: Database session
            model_id: Model ID
            training_samples: Number of training samples
            training_metrics: Training metrics
        
        Returns:
            True if updated successfully
        """
        model = db.query(MLModel).filter(MLModel.id == model_id).first()
        
        if not model:
            return False
        
        model.training_samples = training_samples
        model.training_metrics = training_metrics
        model.trained_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"Updated training info for model: {model.model_name}")
        
        return True
    
    def update_model_performance(
        self,
        db: Session,
        model_id: str,
        performance_metrics: Dict[str, Any]
    ) -> bool:
        """
        Update model performance metrics.
        
        Args:
            db: Database session
            model_id: Model ID
            performance_metrics: Performance metrics
        
        Returns:
            True if updated successfully
        """
        model = db.query(MLModel).filter(MLModel.id == model_id).first()
        
        if not model:
            return False
        
        model.performance_metrics = performance_metrics
        model.last_evaluated_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"Updated performance metrics for model: {model.model_name}")
        
        return True
    
    def set_production_model(
        self,
        db: Session,
        tenant_id: str,
        model_id: str
    ) -> bool:
        """
        Set a model as production model.
        
        Args:
            db: Database session
            tenant_id: Tenant ID
            model_id: Model ID to set as production
        
        Returns:
            True if set successfully
        """
        # Get the model
        model = db.query(MLModel).filter(
            MLModel.id == model_id,
            MLModel.tenant_id == tenant_id
        ).first()
        
        if not model:
            return False
        
        # Deactivate all other production models for this tenant
        db.query(MLModel).filter(
            MLModel.tenant_id == tenant_id,
            MLModel.is_production == True,
            MLModel.id != model_id
        ).update({"is_production": False})
        
        # Set this model as production
        model.is_production = True
        model.is_active = True
        
        db.commit()
        
        logger.info(f"Set model as production: {model.model_name}")
        
        return True
    
    def get_production_model(
        self,
        db: Session,
        tenant_id: str
    ) -> Optional[MLModel]:
        """
        Get production model for tenant.
        
        Args:
            db: Database session
            tenant_id: Tenant ID
        
        Returns:
            Production model or None
        """
        model = db.query(MLModel).filter(
            MLModel.tenant_id == tenant_id,
            MLModel.is_production == True,
            MLModel.is_active == True
        ).first()
        
        return model
    
    def get_models(
        self,
        db: Session,
        tenant_id: str,
        model_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_production: Optional[bool] = None,
        is_shadow: Optional[bool] = None,
        limit: int = 100
    ) -> List[MLModel]:
        """
        Get models with filters.
        
        Args:
            db: Database session
            tenant_id: Tenant ID
            model_type: Filter by model type
            is_active: Filter by active status
            is_production: Filter by production status
            is_shadow: Filter by shadow status
            limit: Maximum number of models to return
        
        Returns:
            List of models
        """
        query = db.query(MLModel).filter(MLModel.tenant_id == tenant_id)
        
        if model_type:
            query = query.filter(MLModel.model_type == model_type)
        
        if is_active is not None:
            query = query.filter(MLModel.is_active == is_active)
        
        if is_production is not None:
            query = query.filter(MLModel.is_production == is_production)
        
        if is_shadow is not None:
            query = query.filter(MLModel.is_shadow == is_shadow)
        
        return query.order_by(MLModel.created_at.desc()).limit(limit).all()
    
    def get_model_by_name(
        self,
        db: Session,
        tenant_id: str,
        model_name: str,
        model_version: Optional[str] = None
    ) -> Optional[MLModel]:
        """
        Get model by name and version.
        
        Args:
            db: Database session
            tenant_id: Tenant ID
            model_name: Model name
            model_version: Model version (latest if None)
        
        Returns:
            Model or None
        """
        query = db.query(MLModel).filter(
            MLModel.tenant_id == tenant_id,
            MLModel.model_name == model_name
        )
        
        if model_version:
            query = query.filter(MLModel.model_version == model_version)
        else:
            query = query.order_by(MLModel.created_at.desc())
        
        return query.first()
    
    def deactivate_model(
        self,
        db: Session,
        model_id: str
    ) -> bool:
        """
        Deactivate a model.
        
        Args:
            db: Database session
            model_id: Model ID
        
        Returns:
            True if deactivated successfully
        """
        model = db.query(MLModel).filter(MLModel.id == model_id).first()
        
        if not model:
            return False
        
        model.is_active = False
        
        # If this was a production model, we need to handle it
        if model.is_production:
            model.is_production = False
            logger.warning(f"Deactivated production model: {model.model_name}")
        
        db.commit()
        
        logger.info(f"Deactivated model: {model.model_name}")
        
        return True
    
    def delete_model(
        self,
        db: Session,
        model_id: str
    ) -> bool:
        """
        Delete a model from registry.
        
        Args:
            db: Database session
            model_id: Model ID
        
        Returns:
            True if deleted successfully
        """
        model = db.query(MLModel).filter(MLModel.id == model_id).first()
        
        if not model:
            return False
        
        db.delete(model)
        db.commit()
        
        logger.info(f"Deleted model from registry: {model.model_name}")
        
        return True


# Global model registry instance
model_registry = ModelRegistry()