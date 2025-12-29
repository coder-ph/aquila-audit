"""
Isolation Forest implementation for anomaly detection.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from typing import Dict, List, Any, Tuple, Optional
import pickle
import joblib
from pathlib import Path
import json

from shared.utils.logging import logger
from services.ml_service.config import config


class IsolationForestAnomalyDetector:
    """Isolation Forest based anomaly detector."""
    
    def __init__(self, model_name: str = "default"):
        self.model_name = model_name
        self.model: Optional[IsolationForest] = None
        self.scaler: Optional[StandardScaler] = None
        self.feature_names: List[str] = []
        self.is_trained: bool = False
        self.metadata: Dict[str, Any] = {}
        
        # Model parameters
        self.contamination = config.isolation_forest_contamination
        self.n_estimators = config.isolation_forest_n_estimators
        self.max_samples = config.isolation_forest_max_samples
        self.random_state = config.random_state
    
    def initialize(self, feature_names: List[str]):
        """Initialize the model with feature names."""
        self.feature_names = feature_names
        self.scaler = StandardScaler()
        self.model = IsolationForest(
            contamination=self.contamination,
            n_estimators=self.n_estimators,
            max_samples=self.max_samples,
            random_state=self.random_state,
            n_jobs=-1
        )
        
        self.metadata = {
            "model_name": self.model_name,
            "feature_names": feature_names,
            "contamination": self.contamination,
            "n_estimators": self.n_estimators,
            "max_samples": self.max_samples,
            "created_at": pd.Timestamp.now().isoformat()
        }
        
        logger.info(f"Initialized Isolation Forest model: {self.model_name}")
    
    def train(self, X: np.ndarray, y: Optional[np.ndarray] = None) -> Dict[str, Any]:
        """
        Train the isolation forest model.
        
        Args:
            X: Feature matrix
            y: Labels (not used for unsupervised)
        
        Returns:
            Training metrics
        """
        if self.model is None:
            raise ValueError("Model not initialized. Call initialize() first.")
        
        if len(X) < config.min_samples_train:
            raise ValueError(
                f"Insufficient training samples: {len(X)}. Minimum required: {config.min_samples_train}"
            )
        
        logger.info(f"Training Isolation Forest on {len(X)} samples")
        
        # Scale features
        X_scaled = self.scaler.fit_transform(X)
        
        # Train model
        self.model.fit(X_scaled)
        
        # Calculate training metrics
        predictions = self.model.predict(X_scaled)
        anomaly_scores = self.model.score_samples(X_scaled)
        
        # Convert predictions: 1 = normal, -1 = anomaly
        anomalies = np.sum(predictions == -1)
        anomaly_percentage = anomalies / len(predictions) * 100
        
        # Update metadata
        self.metadata.update({
            "trained_at": pd.Timestamp.now().isoformat(),
            "training_samples": len(X),
            "anomalies_detected": int(anomalies),
            "anomaly_percentage": float(anomaly_percentage),
            "is_trained": True
        })
        
        self.is_trained = True
        
        metrics = {
            "model_name": self.model_name,
            "training_samples": len(X),
            "features": len(self.feature_names),
            "anomalies_detected": int(anomalies),
            "anomaly_percentage": float(anomaly_percentage),
            "mean_anomaly_score": float(np.mean(anomaly_scores)),
            "std_anomaly_score": float(np.std(anomaly_scores))
        }
        
        logger.info(f"Training complete: {metrics['anomalies_detected']} anomalies detected")
        
        return metrics
    
    def predict(self, X: np.ndarray) -> Dict[str, Any]:
        """
        Predict anomalies on new data.
        
        Args:
            X: Feature matrix
        
        Returns:
            Prediction results
        """
        if not self.is_trained:
            raise ValueError("Model not trained. Call train() first.")
        
        if X.shape[1] != len(self.feature_names):
            raise ValueError(
                f"Feature dimension mismatch: expected {len(self.feature_names)}, got {X.shape[1]}"
            )
        
        # Scale features
        X_scaled = self.scaler.transform(X)
        
        # Predict anomalies
        predictions = self.model.predict(X_scaled)
        anomaly_scores = self.model.score_samples(X_scaled)
        decision_scores = self.model.decision_function(X_scaled)
        
        # Convert to more intuitive format: 0 = normal, 1 = anomaly
        is_anomaly = (predictions == -1).astype(int)
        anomaly_probability = 1 / (1 + np.exp(-decision_scores))  # Sigmoid transform
        
        results = {
            "is_anomaly": is_anomaly.tolist(),
            "anomaly_score": anomaly_scores.tolist(),
            "decision_score": decision_scores.tolist(),
            "anomaly_probability": anomaly_probability.tolist(),
            "predictions_count": len(predictions),
            "anomalies_count": int(np.sum(is_anomaly)),
            "anomaly_percentage": float(np.mean(is_anomaly) * 100)
        }
        
        # Add feature contributions if available
        if hasattr(self.model, 'feature_importances_'):
            feature_importance = self.model.feature_importances_.tolist()
            results["feature_importance"] = dict(zip(self.feature_names, feature_importance))
        
        return results
    
    def predict_single(self, features: Dict[str, float]) -> Dict[str, Any]:
        """
        Predict anomaly for a single record.
        
        Args:
            features: Dictionary of feature values
        
        Returns:
            Single prediction result
        """
        # Convert to array
        feature_vector = np.array([[features.get(f, 0) for f in self.feature_names]])
        
        # Get predictions
        results = self.predict(feature_vector)
        
        # Format single result
        return {
            "is_anomaly": bool(results["is_anomaly"][0]),
            "anomaly_score": float(results["anomaly_score"][0]),
            "anomaly_probability": float(results["anomaly_probability"][0]),
            "features": features,
            "model_name": self.model_name
        }
    
    def save(self, model_dir: Optional[Path] = None) -> Path:
        """
        Save the model to disk.
        
        Args:
            model_dir: Directory to save model
        
        Returns:
            Path to saved model
        """
        if not self.is_trained:
            raise ValueError("Cannot save untrained model")
        
        if model_dir is None:
            model_dir = Path(config.models_dir) / self.model_name
        
        model_dir.mkdir(parents=True, exist_ok=True)
        
        # Save model components
        model_path = model_dir / "model.joblib"
        scaler_path = model_dir / "scaler.joblib"
        metadata_path = model_dir / "metadata.json"
        features_path = model_dir / "features.json"
        
        # Save objects
        joblib.dump(self.model, model_path)
        joblib.dump(self.scaler, scaler_path)
        
        # Save metadata
        with open(metadata_path, 'w') as f:
            json.dump(self.metadata, f, indent=2)
        
        # Save features
        with open(features_path, 'w') as f:
            json.dump({"feature_names": self.feature_names}, f, indent=2)
        
        logger.info(f"Model saved to {model_dir}")
        
        return model_dir
    
    def load(self, model_dir: Path) -> bool:
        """
        Load model from disk.
        
        Args:
            model_dir: Directory containing model files
        
        Returns:
            True if loaded successfully
        """
        try:
            model_path = model_dir / "model.joblib"
            scaler_path = model_dir / "scaler.joblib"
            metadata_path = model_dir / "metadata.json"
            features_path = model_dir / "features.json"
            
            if not all(p.exists() for p in [model_path, scaler_path, metadata_path, features_path]):
                logger.error(f"Missing model files in {model_dir}")
                return False
            
            # Load components
            self.model = joblib.load(model_path)
            self.scaler = joblib.load(scaler_path)
            
            # Load metadata
            with open(metadata_path, 'r') as f:
                self.metadata = json.load(f)
            
            # Load features
            with open(features_path, 'r') as f:
                features_data = json.load(f)
                self.feature_names = features_data["feature_names"]
            
            self.is_trained = True
            self.model_name = model_dir.name
            
            logger.info(f"Model loaded from {model_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Error loading model from {model_dir}: {str(e)}")
            return False
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model information."""
        return {
            "model_name": self.model_name,
            "is_trained": self.is_trained,
            "feature_count": len(self.feature_names),
            "feature_names": self.feature_names,
            "metadata": self.metadata
        }
    
    def explain_anomaly(self, features: Dict[str, float], top_n: int = 5) -> Dict[str, Any]:
        """
        Explain why a record was flagged as anomaly.
        
        Args:
            features: Feature values
            top_n: Number of top contributing features to return
        
        Returns:
            Explanation of anomaly
        """
        if not self.is_trained:
            raise ValueError("Model not trained")
        
        # Get prediction
        prediction = self.predict_single(features)
        
        if not prediction["is_anomaly"]:
            return {
                "is_anomaly": False,
                "message": "Record is not an anomaly"
            }
        
        # Calculate feature deviations from training distribution
        deviations = {}
        for feature_name in self.feature_names:
            feature_value = features.get(feature_name, 0)
            
            # Get training statistics from scaler
            mean = self.scaler.mean_[self.feature_names.index(feature_name)]
            std = self.scaler.scale_[self.feature_names.index(feature_name)]
            
            if std > 0:
                z_score = abs((feature_value - mean) / std)
                deviations[feature_name] = {
                    "value": feature_value,
                    "mean": float(mean),
                    "std": float(std),
                    "z_score": float(z_score),
                    "deviation": float(z_score * std)
                }
        
        # Sort by deviation
        sorted_deviations = sorted(
            deviations.items(),
            key=lambda x: x[1]["z_score"],
            reverse=True
        )
        
        explanation = {
            "is_anomaly": True,
            "anomaly_score": prediction["anomaly_score"],
            "anomaly_probability": prediction["anomaly_probability"],
            "top_contributing_features": dict(sorted_deviations[:top_n]),
            "message": f"Record flagged as anomaly with score {prediction['anomaly_score']:.3f}"
        }
        
        return explanation