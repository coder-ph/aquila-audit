"""
Shadow mode implementation for safe ML model deployment.
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import json
from pathlib import Path

from shared.utils.logging import logger
from services.ml_service.config import config
from .isolation_forest import IsolationForestAnomalyDetector
from .feature_extractor import FeatureExtractor


class ShadowModeManager:
    """Manages shadow mode deployment for ML models."""
    
    def __init__(self, model_name: str = "shadow_mode"):
        self.model_name = model_name
        self.production_model: Optional[IsolationForestAnomalyDetector] = None
        self.shadow_model: Optional[IsolationForestAnomalyDetector] = None
        self.feature_extractor = FeatureExtractor()
        self.is_active = config.shadow_mode_enabled
        self.comparison_results: List[Dict[str, Any]] = []
        
        # Performance tracking
        self.performance_metrics: Dict[str, List[float]] = {
            "agreement_rate": [],
            "production_anomaly_rate": [],
            "shadow_anomaly_rate": [],
            "false_positive_rate": [],
            "false_negative_rate": []
        }
    
    def initialize(self, production_model: IsolationForestAnomalyDetector):
        """Initialize shadow mode with production model."""
        self.production_model = production_model
        
        # Create shadow model with same configuration
        self.shadow_model = IsolationForestAnomalyDetector(
            model_name=f"{self.model_name}_shadow"
        )
        
        # Initialize shadow model with same features
        self.shadow_model.initialize(self.production_model.feature_names)
        
        logger.info(f"Shadow mode initialized for model: {production_model.model_name}")
    
    def train_shadow_model(self, X: np.ndarray, y: Optional[np.ndarray] = None):
        """Train shadow model on data."""
        if self.shadow_model is None:
            raise ValueError("Shadow model not initialized")
        
        logger.info("Training shadow model")
        
        # Train shadow model
        metrics = self.shadow_model.train(X, y)
        
        logger.info(f"Shadow model trained: {metrics}")
        
        return metrics
    
    def compare_predictions(
        self,
        X: np.ndarray,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Compare predictions between production and shadow models.
        
        Args:
            X: Feature matrix
            metadata: Additional metadata about the data
        
        Returns:
            Comparison results
        """
        if self.production_model is None or self.shadow_model is None:
            raise ValueError("Models not initialized")
        
        if not self.production_model.is_trained or not self.shadow_model.is_trained:
            raise ValueError("Models not trained")
        
        # Get predictions from both models
        prod_results = self.production_model.predict(X)
        shadow_results = self.shadow_model.predict(X)
        
        # Compare predictions
        prod_anomalies = np.array(prod_results["is_anomaly"])
        shadow_anomalies = np.array(shadow_results["is_anomaly"])
        
        # Calculate agreement metrics
        agreement = np.sum(prod_anomalies == shadow_anomalies)
        disagreement = np.sum(prod_anomalies != shadow_anomalies)
        total = len(prod_anomalies)
        
        agreement_rate = agreement / total * 100
        disagreement_rate = disagreement / total * 100
        
        # Calculate confusion matrix
        true_positives = np.sum((prod_anomalies == 1) & (shadow_anomalies == 1))
        false_positives = np.sum((prod_anomalies == 1) & (shadow_anomalies == 0))
        false_negatives = np.sum((prod_anomalies == 0) & (shadow_anomalies == 1))
        true_negatives = np.sum((prod_anomalies == 0) & (shadow_anomalies == 0))
        
        # Calculate rates
        prod_anomaly_rate = np.mean(prod_anomalies) * 100
        shadow_anomaly_rate = np.mean(shadow_anomalies) * 100
        
        if (true_positives + false_positives) > 0:
            false_positive_rate = false_positives / (true_positives + false_positives) * 100
        else:
            false_positive_rate = 0
        
        if (true_positives + false_negatives) > 0:
            false_negative_rate = false_negatives / (true_positives + false_negatives) * 100
        else:
            false_negative_rate = 0
        
        # Create comparison result
        comparison = {
            "timestamp": datetime.utcnow().isoformat(),
            "total_records": total,
            "agreement_rate": float(agreement_rate),
            "disagreement_rate": float(disagreement_rate),
            "production_anomaly_rate": float(prod_anomaly_rate),
            "shadow_anomaly_rate": float(shadow_anomaly_rate),
            "confusion_matrix": {
                "true_positives": int(true_positives),
                "false_positives": int(false_positives),
                "false_negatives": int(false_negatives),
                "true_negatives": int(true_negatives)
            },
            "performance_metrics": {
                "false_positive_rate": float(false_positive_rate),
                "false_negative_rate": float(false_negative_rate)
            },
            "metadata": metadata or {}
        }
        
        # Store comparison
        self.comparison_results.append(comparison)
        
        # Update performance tracking
        self.performance_metrics["agreement_rate"].append(agreement_rate)
        self.performance_metrics["production_anomaly_rate"].append(prod_anomaly_rate)
        self.performance_metrics["shadow_anomaly_rate"].append(shadow_anomaly_rate)
        self.performance_metrics["false_positive_rate"].append(false_positive_rate)
        self.performance_metrics["false_negative_rate"].append(false_negative_rate)
        
        # Check if shadow model is performing well enough for promotion
        if agreement_rate >= config.shadow_mode_threshold * 100:
            comparison["promotion_recommended"] = True
            comparison["promotion_reason"] = f"High agreement rate: {agreement_rate:.1f}%"
        else:
            comparison["promotion_recommended"] = False
            comparison["promotion_reason"] = f"Low agreement rate: {agreement_rate:.1f}%"
        
        logger.info(f"Shadow mode comparison: {agreement_rate:.1f}% agreement")
        
        return comparison
    
    def promote_shadow_model(self) -> bool:
        """
        Promote shadow model to production.
        
        Returns:
            True if promotion was successful
        """
        if self.shadow_model is None or self.production_model is None:
            logger.error("Models not initialized for promotion")
            return False
        
        # Check recent performance
        if len(self.performance_metrics["agreement_rate"]) < 10:
            logger.warning("Insufficient data for promotion decision")
            return False
        
        # Calculate average agreement rate
        recent_agreement = self.performance_metrics["agreement_rate"][-10:]
        avg_agreement = np.mean(recent_agreement)
        
        if avg_agreement >= config.shadow_mode_threshold * 100:
            # Swap models
            self.production_model, self.shadow_model = self.shadow_model, self.production_model
            
            # Update model names
            self.production_model.model_name = self.production_model.model_name.replace("_shadow", "")
            self.shadow_model.model_name = f"{self.model_name}_shadow"
            
            logger.info(f"Shadow model promoted to production. Average agreement: {avg_agreement:.1f}%")
            
            # Save promoted model
            model_dir = Path(config.models_dir) / self.production_model.model_name
            self.production_model.save(model_dir)
            
            return True
        else:
            logger.info(f"Shadow model not promoted. Average agreement: {avg_agreement:.1f}% (threshold: {config.shadow_mode_threshold*100}%)")
            return False
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get summary of shadow mode performance."""
        if not self.performance_metrics["agreement_rate"]:
            return {"message": "No performance data available"}
        
        summary = {
            "total_comparisons": len(self.comparison_results),
            "average_agreement_rate": float(np.mean(self.performance_metrics["agreement_rate"])),
            "average_production_anomaly_rate": float(np.mean(self.performance_metrics["production_anomaly_rate"])),
            "average_shadow_anomaly_rate": float(np.mean(self.performance_metrics["shadow_anomaly_rate"])),
            "recent_performance": {
                "last_10_agreement": [float(x) for x in self.performance_metrics["agreement_rate"][-10:]],
                "last_10_avg_agreement": float(np.mean(self.performance_metrics["agreement_rate"][-10:])),
                "promotion_ready": len(self.performance_metrics["agreement_rate"]) >= 10 and 
                                  np.mean(self.performance_metrics["agreement_rate"][-10:]) >= config.shadow_mode_threshold * 100
            },
            "models": {
                "production": self.production_model.get_model_info() if self.production_model else None,
                "shadow": self.shadow_model.get_model_info() if self.shadow_model else None
            }
        }
        
        return summary
    
    def save_comparison_results(self, filepath: str):
        """Save comparison results to file."""
        results = {
            "comparison_results": self.comparison_results,
            "performance_metrics": self.performance_metrics,
            "summary": self.get_performance_summary(),
            "saved_at": datetime.utcnow().isoformat()
        }
        
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"Comparison results saved to {filepath}")
    
    def load_comparison_results(self, filepath: str) -> bool:
        """Load comparison results from file."""
        try:
            with open(filepath, 'r') as f:
                results = json.load(f)
            
            self.comparison_results = results.get("comparison_results", [])
            self.performance_metrics = results.get("performance_metrics", {
                "agreement_rate": [],
                "production_anomaly_rate": [],
                "shadow_anomaly_rate": [],
                "false_positive_rate": [],
                "false_negative_rate": []
            })
            
            logger.info(f"Comparison results loaded from {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Error loading comparison results: {str(e)}")
            return False
    
    def analyze_disagreements(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """
        Analyze cases where models disagree.
        
        Args:
            top_n: Number of top disagreements to analyze
        
        Returns:
            List of disagreement analyses
        """
        if not self.comparison_results:
            return []
        
        # Collect all disagreements
        all_disagreements = []
        
        for comparison in self.comparison_results[-100:]:  # Last 100 comparisons
            if "disagreement_details" in comparison:
                all_disagreements.extend(comparison["disagreement_details"])
        
        # Sort by confidence difference
        sorted_disagreements = sorted(
            all_disagreements,
            key=lambda x: abs(x.get("confidence_difference", 0)),
            reverse=True
        )[:top_n]
        
        return sorted_disagreements