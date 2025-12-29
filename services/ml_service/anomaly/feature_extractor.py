"""
Feature extraction from data for anomaly detection.
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime
import json
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.impute import SimpleImputer

from shared.utils.logging import logger


class FeatureExtractor:
    """Extracts and prepares features for anomaly detection."""
    
    def __init__(self):
        self.numerical_features: List[str] = []
        self.categorical_features: List[str] = []
        self.datetime_features: List[str] = []
        self.feature_config: Dict[str, Any] = {}
        self.scaler = StandardScaler()
        self.encoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
        self.imputer = SimpleImputer(strategy='median')
        
    def analyze_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze dataframe to determine feature types.
        
        Args:
            df: Input dataframe
        
        Returns:
            Feature analysis
        """
        analysis = {
            "total_records": len(df),
            "total_features": len(df.columns),
            "feature_types": {},
            "missing_values": {},
            "data_types": {}
        }
        
        for column in df.columns:
            # Determine data type
            dtype = str(df[column].dtype)
            analysis["data_types"][column] = dtype
            
            # Count missing values
            missing = df[column].isnull().sum()
            missing_pct = missing / len(df) * 100
            analysis["missing_values"][column] = {
                "count": int(missing),
                "percentage": float(missing_pct)
            }
            
            # Determine feature type
            if dtype.startswith('datetime'):
                self.datetime_features.append(column)
                feature_type = "datetime"
            elif dtype in ['object', 'category', 'bool']:
                self.categorical_features.append(column)
                feature_type = "categorical"
                # Get unique values
                unique_count = df[column].nunique()
                analysis["feature_types"][column] = {
                    "type": feature_type,
                    "unique_values": int(unique_count)
                }
            else:
                self.numerical_features.append(column)
                feature_type = "numerical"
                # Get statistics
                if missing < len(df):  # Only if not all missing
                    analysis["feature_types"][column] = {
                        "type": feature_type,
                        "min": float(df[column].min()),
                        "max": float(df[column].max()),
                        "mean": float(df[column].mean()),
                        "std": float(df[column].std()),
                        "median": float(df[column].median())
                    }
        
        # Store configuration
        self.feature_config = {
            "numerical_features": self.numerical_features,
            "categorical_features": self.categorical_features,
            "datetime_features": self.datetime_features,
            "total_features": len(df.columns),
            "analysis_timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Analyzed {len(df)} records with {len(df.columns)} features")
        
        return analysis
    
    def extract_features(self, df: pd.DataFrame, training: bool = True) -> Tuple[np.ndarray, List[str]]:
        """
        Extract features from dataframe.
        
        Args:
            df: Input dataframe
            training: Whether this is training data
        
        Returns:
            Tuple of (feature_matrix, feature_names)
        """
        # Make a copy to avoid modifying original
        df_processed = df.copy()
        
        # Handle datetime features
        for col in self.datetime_features:
            if col in df_processed.columns:
                # Extract useful datetime features
                df_processed[f"{col}_year"] = pd.to_datetime(df_processed[col]).dt.year
                df_processed[f"{col}_month"] = pd.to_datetime(df_processed[col]).dt.month
                df_processed[f"{col}_day"] = pd.to_datetime(df_processed[col]).dt.day
                df_processed[f"{col}_dayofweek"] = pd.to_datetime(df_processed[col]).dt.dayofweek
                df_processed[f"{col}_hour"] = pd.to_datetime(df_processed[col]).dt.hour
                
                # Add to numerical features
                self.numerical_features.extend([
                    f"{col}_year", f"{col}_month", f"{col}_day",
                    f"{col}_dayofweek", f"{col}_hour"
                ])
        
        # Process numerical features
        numerical_data = df_processed[self.numerical_features].copy()
        
        # Handle missing values
        numerical_data = pd.DataFrame(
            self.imputer.fit_transform(numerical_data) if training else self.imputer.transform(numerical_data),
            columns=self.numerical_features
        )
        
        # Scale numerical features
        if training:
            numerical_scaled = self.scaler.fit_transform(numerical_data)
        else:
            numerical_scaled = self.scaler.transform(numerical_data)
        
        # Process categorical features
        categorical_features = []
        if self.categorical_features:
            categorical_data = df_processed[self.categorical_features].copy()
            
            # Fill missing categorical values
            categorical_data = categorical_data.fillna('MISSING')
            
            # Encode categorical features
            if training:
                encoded = self.encoder.fit_transform(categorical_data)
                categorical_features = self.encoder.get_feature_names_out(self.categorical_features).tolist()
            else:
                encoded = self.encoder.transform(categorical_data)
                categorical_features = self.encoder.get_feature_names_out(self.categorical_features).tolist()
        else:
            encoded = np.array([])
        
        # Combine all features
        if encoded.size > 0:
            features = np.hstack([numerical_scaled, encoded])
            all_feature_names = self.numerical_features + categorical_features
        else:
            features = numerical_scaled
            all_feature_names = self.numerical_features
        
        # Limit features if too many
        if len(all_feature_names) > 50:  # Adjust as needed
            logger.warning(f"Too many features ({len(all_feature_names)}), limiting to 50")
            features = features[:, :50]
            all_feature_names = all_feature_names[:50]
        
        logger.info(f"Extracted {features.shape[1]} features from {len(df)} records")
        
        return features, all_feature_names
    
    def create_derived_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create derived features for anomaly detection.
        
        Args:
            df: Input dataframe
        
        Returns:
            Dataframe with derived features
        """
        df_derived = df.copy()
        
        # Create statistical features for numerical columns
        for col in self.numerical_features:
            if col in df_derived.columns:
                # Rolling statistics
                if len(df_derived) > 10:
                    df_derived[f"{col}_rolling_mean_5"] = df_derived[col].rolling(5, min_periods=1).mean()
                    df_derived[f"{col}_rolling_std_5"] = df_derived[col].rolling(5, min_periods=1).std()
                
                # Percent change
                df_derived[f"{col}_pct_change"] = df_derived[col].pct_change().fillna(0)
                
                # Z-score (within this dataset)
                mean = df_derived[col].mean()
                std = df_derived[col].std()
                if std > 0:
                    df_derived[f"{col}_zscore"] = (df_derived[col] - mean) / std
        
        # Create interaction features
        if len(self.numerical_features) >= 2:
            for i, col1 in enumerate(self.numerical_features[:3]):
                for col2 in self.numerical_features[i+1:4]:
                    if col1 in df_derived.columns and col2 in df_derived.columns:
                        df_derived[f"{col1}_times_{col2}"] = df_derived[col1] * df_derived[col2]
                        df_derived[f"{col1}_div_{col2}"] = df_derived[col1] / (df_derived[col2].replace(0, 1))
        
        # Create frequency features for categorical columns
        for col in self.categorical_features:
            if col in df_derived.columns:
                freq = df_derived[col].value_counts(normalize=True)
                df_derived[f"{col}_frequency"] = df_derived[col].map(freq).fillna(0)
        
        return df_derived
    
    def get_feature_importance(self, model, feature_names: List[str]) -> Dict[str, float]:
        """
        Extract feature importance from trained model.
        
        Args:
            model: Trained model with feature_importances_ attribute
            feature_names: List of feature names
        
        Returns:
            Dictionary of feature importance scores
        """
        if hasattr(model, 'feature_importances_'):
            importance_scores = model.feature_importances_
            
            if len(importance_scores) != len(feature_names):
                logger.warning(f"Feature importance dimension mismatch: {len(importance_scores)} != {len(feature_names)}")
                return {}
            
            # Create dictionary
            importance_dict = dict(zip(feature_names, importance_scores))
            
            # Sort by importance
            sorted_importance = dict(
                sorted(importance_dict.items(), key=lambda x: x[1], reverse=True)
            )
            
            return sorted_importance
        
        else:
            logger.warning("Model does not have feature_importances_ attribute")
            return {}
    
    def save_config(self, filepath: str):
        """Save feature configuration to file."""
        config = {
            "feature_config": self.feature_config,
            "numerical_features": self.numerical_features,
            "categorical_features": self.categorical_features,
            "datetime_features": self.datetime_features,
            "scaler_params": {
                "mean": self.scaler.mean_.tolist() if hasattr(self.scaler, 'mean_') else [],
                "scale": self.scaler.scale_.tolist() if hasattr(self.scaler, 'scale_') else []
            } if hasattr(self.scaler, 'mean_') else {}
        }
        
        with open(filepath, 'w') as f:
            json.dump(config, f, indent=2)
        
        logger.info(f"Feature configuration saved to {filepath}")
    
    def load_config(self, filepath: str) -> bool:
        """Load feature configuration from file."""
        try:
            with open(filepath, 'r') as f:
                config = json.load(f)
            
            self.feature_config = config.get("feature_config", {})
            self.numerical_features = config.get("numerical_features", [])
            self.categorical_features = config.get("categorical_features", [])
            self.datetime_features = config.get("datetime_features", [])
            
            # Load scaler parameters if available
            if "scaler_params" in config:
                scaler_params = config["scaler_params"]
                if scaler_params.get("mean") and scaler_params.get("scale"):
                    self.scaler.mean_ = np.array(scaler_params["mean"])
                    self.scaler.scale_ = np.array(scaler_params["scale"])
            
            logger.info(f"Feature configuration loaded from {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Error loading feature configuration: {str(e)}")
            return False