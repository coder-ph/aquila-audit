"""
Model manager for ML models.
"""
import json
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime
import numpy as np

from shared.utils.logging import logger
from services.ml_service.config import config
from services.ml_service.anomaly.isolation_forest import IsolationForestAnomalyDetector
from services.ml_service.anomaly.feature_extractor import FeatureExtractor
from services.ml_service.anomaly.shadow_mode import ShadowModeManager


class ModelManager:
    """Manages ML models and their lifecycle."""
    
    def __init__(self):
        self.models: Dict[str, IsolationForestAnomalyDetector] = {}
        self.feature_extractors: Dict[str, FeatureExtractor] = {}
        self.shadow_managers: Dict[str, ShadowModeManager] = {}
        self.model_registry: Dict[str, Dict[str, Any]] = {}
        
        # Create models directory
        self.models_dir = Path(config.models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
    
    def load_all_models(self) -> int:
        """
        Load all models from disk.
        
        Returns:
            Number of models loaded
        """
        loaded_count = 0
        
        # Scan models directory
        for model_dir in self.models_dir.iterdir():
            if model_dir.is_dir():
                try:
                    # Check if this is a valid model directory
                    model_files = list(model_dir.glob("*"))
                    if any(f.name == "model.joblib" for f in model_files):
                        # Load model
                        model = IsolationForestAnomalyDetector(model_name=model_dir.name)
                        if model.load(model_dir):
                            self.models[model_dir.name] = model
                            loaded_count += 1
                            
                            # Load feature extractor if available
                            feature_config = model_dir / "feature_config.json"
                            if feature_config.exists():
                                feature_extractor = FeatureExtractor()
                                if feature_extractor.load_config(str(feature_config)):
                                    self.feature_extractors[model_dir.name] = feature_extractor
                            
                            logger.info(f"Loaded model: {model_dir.name}")
                except Exception as e:
                    logger.error(f"Error loading model from {model_dir}: {str(e)}")
        
        # Initialize shadow mode for default model
        if config.default_model in self.models and config.shadow_mode_enabled:
            self.initialize_shadow_mode(config.default_model)
        
        logger.info(f"Loaded {loaded_count} models")
        return loaded_count
    
    def get_model(self, model_name: str) -> Optional[IsolationForestAnomalyDetector]:
        """Get model by name."""
        return self.models.get(model_name)
    
    def create_model(
        self,
        model_name: str,
        feature_names: List[str],
        description: str = ""
    ) -> IsolationForestAnomalyDetector:
        """
        Create a new model.
        
        Args:
            model_name: Name of the model
            feature_names: List of feature names
            description: Model description
        
        Returns:
            Created model
        """
        if model_name in self.models:
            raise ValueError(f"Model '{model_name}' already exists")
        
        # Create model
        model = IsolationForestAnomalyDetector(model_name=model_name)
        model.initialize(feature_names)
        
        # Store model
        self.models[model_name] = model
        
        # Update registry
        self.model_registry[model_name] = {
            "name": model_name,
            "description": description,
            "feature_count": len(feature_names),
            "feature_names": feature_names,
            "created_at": datetime.utcnow().isoformat(),
            "is_trained": False,
            "type": "isolation_forest"
        }
        
        logger.info(f"Created model: {model_name} with {len(feature_names)} features")
        
        return model
    
    def train_model(
        self,
        model_name: str,
        X: np.ndarray,
        feature_extractor: Optional[FeatureExtractor] = None
    ) -> Dict[str, Any]:
        """
        Train a model.
        
        Args:
            model_name: Name of the model
            X: Training data
            feature_extractor: Feature extractor (optional)
        
        Returns:
            Training metrics
        """
        model = self.get_model(model_name)
        if model is None:
            raise ValueError(f"Model '{model_name}' not found")
        
        # Train model
        metrics = model.train(X)
        
        # Save model
        model_dir = self.models_dir / model_name
        model.save(model_dir)
        
        # Save feature extractor if provided
        if feature_extractor:
            self.feature_extractors[model_name] = feature_extractor
            feature_extractor.save_config(str(model_dir / "feature_config.json"))
        
        # Update registry
        self.model_registry[model_name].update({
            "is_trained": True,
            "trained_at": datetime.utcnow().isoformat(),
            "training_samples": metrics["training_samples"],
            "metrics": metrics
        })
        
        # Initialize shadow mode if enabled
        if config.shadow_mode_enabled and model_name == config.default_model:
            self.initialize_shadow_mode(model_name)
        
        logger.info(f"Trained model: {model_name}")
        
        return metrics
    
    def predict(
        self,
        model_name: str,
        X: np.ndarray,
        include_shadow: bool = False
    ) -> Dict[str, Any]:
        """
        Make predictions with a model.
        
        Args:
            model_name: Name of the model
            X: Input data
            include_shadow: Whether to include shadow mode comparison
        
        Returns:
            Prediction results
        """
        model = self.get_model(model_name)
        if model is None:
            raise ValueError(f"Model '{model_name}' not found")
        
        if not model.is_trained:
            raise ValueError(f"Model '{model_name}' is not trained")
        
        # Get production model predictions
        results = model.predict(X)
        results["model_name"] = model_name
        
        # Include shadow mode comparison if requested and available
        if include_shadow and model_name in self.shadow_managers:
            shadow_manager = self.shadow_managers[model_name]
            
            # Compare with shadow model
            comparison = shadow_manager.compare_predictions(X, {
                "batch_size": len(X),
                "timestamp": datetime.utcnow().isoformat()
            })
            
            results["shadow_mode"] = {
                "comparison": comparison,
                "shadow_model_performance": shadow_manager.get_performance_summary()
            }
        
        return results
    
    def initialize_shadow_mode(self, model_name: str) -> ShadowModeManager:
        """
        Initialize shadow mode for a model.
        
        Args:
            model_name: Name of the model
        
        Returns:
            Shadow mode manager
        """
        model = self.get_model(model_name)
        if model is None:
            raise ValueError(f"Model '{model_name}' not found")
        
        # Create shadow mode manager
        shadow_manager = ShadowModeManager(model_name=model_name)
        shadow_manager.initialize(model)
        
        # Store shadow manager
        self.shadow_managers[model_name] = shadow_manager
        
        logger.info(f"Initialized shadow mode for model: {model_name}")
        
        return shadow_manager
    
    def train_shadow_model(
        self,
        model_name: str,
        X: np.ndarray,
        y: Optional[np.ndarray] = None
    ) -> Dict[str, Any]:
        """
        Train shadow model.
        
        Args:
            model_name: Name of the model
            X: Training data
            y: Labels (optional)
        
        Returns:
            Training metrics
        """
        if model_name not in self.shadow_managers:
            raise ValueError(f"Shadow mode not initialized for model '{model_name}'")
        
        shadow_manager = self.shadow_managers[model_name]
        
        # Train shadow model
        metrics = shadow_manager.train_shadow_model(X, y)
        
        logger.info(f"Trained shadow model for: {model_name}")
        
        return metrics
    
    def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """Get information about a model."""
        model = self.get_model(model_name)
        if model is None:
            raise ValueError(f"Model '{model_name}' not found")
        
        info = model.get_model_info()
        info["registry"] = self.model_registry.get(model_name, {})
        
        # Add shadow mode info if available
        if model_name in self.shadow_managers:
            shadow_manager = self.shadow_managers[model_name]
            info["shadow_mode"] = {
                "is_active": shadow_manager.is_active,
                "performance_summary": shadow_manager.get_performance_summary()
            }
        
        return info
    
    def list_models(self) -> List[Dict[str, Any]]:
        """List all available models."""
        models_list = []
        
        for model_name, model in self.models.items():
            model_info = {
                "name": model_name,
                "is_trained": model.is_trained,
                "feature_count": len(model.feature_names),
                "created_at": self.model_registry.get(model_name, {}).get("created_at"),
                "has_shadow_mode": model_name in self.shadow_managers
            }
            models_list.append(model_info)
        
        return models_list
    
    def get_model_count(self) -> int:
        """Get total number of models."""
        return len(self.models)
    
    def delete_model(self, model_name: str) -> bool:
        """
        Delete a model.
        
        Args:
            model_name: Name of the model to delete
        
        Returns:
            True if deleted successfully
        """
        if model_name not in self.models:
            return False
        
        try:
            # Remove from memory
            del self.models[model_name]
            
            # Remove feature extractor if exists
            if model_name in self.feature_extractors:
                del self.feature_extractors[model_name]
            
            # Remove shadow manager if exists
            if model_name in self.shadow_managers:
                del self.shadow_managers[model_name]
            
            # Remove from registry
            if model_name in self.model_registry:
                del self.model_registry[model_name]
            
            # Delete from disk
            model_dir = self.models_dir / model_name
            if model_dir.exists():
                import shutil
                shutil.rmtree(model_dir)
            
            logger.info(f"Deleted model: {model_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting model {model_name}: {str(e)}")
            return False
    
    def export_model(self, model_name: str, export_dir: Path) -> bool:
        """
        Export model to directory.
        
        Args:
            model_name: Name of the model
            export_dir: Directory to export to
        
        Returns:
            True if exported successfully
        """
        model = self.get_model(model_name)
        if model is None:
            return False
        
        try:
            # Create export directory
            export_dir.mkdir(parents=True, exist_ok=True)
            
            # Save model to export directory
            model.save(export_dir)
            
            # Export feature extractor if available
            if model_name in self.feature_extractors:
                feature_extractor = self.feature_extractors[model_name]
                feature_extractor.save_config(str(export_dir / "feature_config.json"))
            
            # Export registry information
            registry_info = self.model_registry.get(model_name, {})
            with open(export_dir / "registry.json", 'w') as f:
                json.dump(registry_info, f, indent=2)
            
            logger.info(f"Exported model {model_name} to {export_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting model {model_name}: {str(e)}")
            return False
    
    def import_model(self, import_dir: Path) -> bool:
        """
        Import model from directory.
        
        Args:
            import_dir: Directory containing model files
        
        Returns:
            True if imported successfully
        """
        try:
            # Load model
            model_name = import_dir.name
            model = IsolationForestAnomalyDetector(model_name=model_name)
            
            if not model.load(import_dir):
                return False
            
            # Load feature extractor if available
            feature_extractor = None
            feature_config = import_dir / "feature_config.json"
            if feature_config.exists():
                feature_extractor = FeatureExtractor()
                if not feature_extractor.load_config(str(feature_config)):
                    feature_extractor = None
            
            # Load registry info if available
            registry_info = {}
            registry_file = import_dir / "registry.json"
            if registry_file.exists():
                with open(registry_file, 'r') as f:
                    registry_info = json.load(f)
            
            # Store model
            self.models[model_name] = model
            
            if feature_extractor:
                self.feature_extractors[model_name] = feature_extractor
            
            self.model_registry[model_name] = registry_info
            
            logger.info(f"Imported model: {model_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error importing model from {import_dir}: {str(e)}")
            return False


# Global model manager instance
model_manager = ModelManager()