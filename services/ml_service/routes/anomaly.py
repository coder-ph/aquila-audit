from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, UploadFile, File
from sqlalchemy.orm import Session
from uuid import UUID
import pandas as pd
import numpy as np
from io import StringIO
from datetime import datetime
from config import config

from shared.database.session import get_session
from shared.models.file_models import File as FileModel
from shared.utils.logging import logger

from services.api_gateway.dependencies.auth import get_current_user_with_tenant
from services.ml_service.models.model_manager import model_manager
from services.ml_service.anomaly.feature_extractor import FeatureExtractor
from services.ml_service.anomaly.shadow_mode import ShadowModeManager

# Create router
router = APIRouter()


@router.post("/detect/file/{file_id}")
async def detect_anomalies_in_file(
    file_id: UUID,
    model_name: str = Query(config.default_model, description="Model to use for detection"),
    include_shadow: bool = Query(False, description="Include shadow mode comparison"),
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session)
):
    """
    Detect anomalies in a processed file.
    """
    user_id, tenant_id = user_info
    
    # Get file
    file = db.query(FileModel).filter(
        FileModel.id == file_id,
        FileModel.tenant_id == tenant_id
    ).first()
    
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    if file.status != "PROCESSED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be processed before anomaly detection"
        )
    
    # Get model
    model = model_manager.get_model(model_name)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_name}' not found"
        )
    
    if not model.is_trained:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Model '{model_name}' is not trained"
        )
    
    try:
        # Read file based on type
        import json
        from pathlib import Path
        
        file_path = Path(file.storage_path)
        
        if file.file_type == ".csv":
            df = pd.read_csv(file_path)
        elif file.file_type in [".xlsx", ".xls"]:
            df = pd.read_excel(file_path)
        elif file.file_type == ".json":
            with open(file_path, 'r') as f:
                data = json.load(f)
            if isinstance(data, list):
                df = pd.DataFrame(data)
            else:
                df = pd.DataFrame([data])
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type: {file.file_type}"
            )
        
        # Extract features
        feature_extractor = FeatureExtractor()
        feature_extractor.analyze_data(df)
        
        # Get feature extractor for model if available
        model_feature_extractor = model_manager.feature_extractors.get(model_name)
        if model_feature_extractor:
            # Use model's feature extractor
            features, feature_names = model_feature_extractor.extract_features(df, training=False)
        else:
            # Extract features
            features, feature_names = feature_extractor.extract_features(df, training=False)
        
        # Check feature compatibility
        if set(feature_names) != set(model.feature_names):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Feature mismatch. Model expects: {model.feature_names}"
            )
        
        # Reorder features to match model
        feature_order = [model.feature_names.index(f) for f in feature_names]
        features_ordered = features[:, feature_order]
        
        # Predict anomalies
        results = model_manager.predict(
            model_name=model_name,
            X=features_ordered,
            include_shadow=include_shadow
        )
        
        # Add file information
        results["file_info"] = {
            "file_id": str(file_id),
            "filename": file.original_filename,
            "records_processed": len(df),
            "features_used": len(feature_names)
        }
        
        # Add sample anomalies
        anomaly_indices = np.where(np.array(results["is_anomaly"]) == 1)[0]
        if len(anomaly_indices) > 0:
            sample_anomalies = []
            for idx in anomaly_indices[:5]:  # First 5 anomalies
                sample_anomalies.append({
                    "record_index": int(idx),
                    "anomaly_score": float(results["anomaly_score"][idx]),
                    "anomaly_probability": float(results["anomaly_probability"][idx]),
                    "sample_data": df.iloc[idx].to_dict() if idx < len(df) else {}
                })
            results["sample_anomalies"] = sample_anomalies
        
        logger.info(
            f"Anomaly detection completed for file {file_id}: {results['anomalies_count']} anomalies",
            tenant_id=str(tenant_id)
        )
        
        return results
        
    except Exception as e:
        logger.error(f"Error detecting anomalies: {str(e)}", tenant_id=str(tenant_id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Anomaly detection failed: {str(e)}"
        )


@router.post("/detect/data")
async def detect_anomalies_in_data(
    data: List[Dict[str, Any]] = Body(...),
    model_name: str = Query(config.default_model, description="Model to use for detection"),
    include_shadow: bool = Query(False, description="Include shadow mode comparison"),
    user_info: tuple = Depends(get_current_user_with_tenant)
):
    """
    Detect anomalies in provided data.
    """
    user_id, tenant_id = user_info
    
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No data provided"
        )
    
    # Get model
    model = model_manager.get_model(model_name)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_name}' not found"
        )
    
    if not model.is_trained:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Model '{model_name}' is not trained"
        )
    
    try:
        # Convert data to DataFrame
        df = pd.DataFrame(data)
        
        # Extract features
        feature_extractor = FeatureExtractor()
        feature_extractor.analyze_data(df)
        
        # Get feature extractor for model if available
        model_feature_extractor = model_manager.feature_extractors.get(model_name)
        if model_feature_extractor:
            # Use model's feature extractor
            features, feature_names = model_feature_extractor.extract_features(df, training=False)
        else:
            # Extract features
            features, feature_names = feature_extractor.extract_features(df, training=False)
        
        # Check feature compatibility
        if set(feature_names) != set(model.feature_names):
            # Try to align features
            available_features = set(feature_names)
            expected_features = set(model.feature_names)
            
            missing_features = expected_features - available_features
            extra_features = available_features - expected_features
            
            if missing_features:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Missing features: {list(missing_features)}"
                )
            
            # Use only expected features
            features = features[:, [feature_names.index(f) for f in model.feature_names]]
        
        # Predict anomalies
        results = model_manager.predict(
            model_name=model_name,
            X=features,
            include_shadow=include_shadow
        )
        
        # Add data information
        results["data_info"] = {
            "records_processed": len(data),
            "features_used": len(model.feature_names)
        }
        
        # Add anomaly details
        anomaly_details = []
        for i, is_anomaly in enumerate(results["is_anomaly"]):
            if is_anomaly:
                anomaly_details.append({
                    "record_index": i,
                    "anomaly_score": results["anomaly_score"][i],
                    "anomaly_probability": results["anomaly_probability"][i],
                    "data": data[i] if i < len(data) else {}
                })
        
        results["anomaly_details"] = anomaly_details
        
        logger.info(
            f"Anomaly detection completed on {len(data)} records: {results['anomalies_count']} anomalies",
            tenant_id=str(tenant_id)
        )
        
        return results
        
    except Exception as e:
        logger.error(f"Error detecting anomalies: {str(e)}", tenant_id=str(tenant_id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Anomaly detection failed: {str(e)}"
        )


@router.post("/train")
async def train_anomaly_model(
    file_id: UUID = Query(..., description="File to use for training"),
    model_name: str = Query(None, description="Name for new model (optional)"),
    description: str = Query("", description="Model description"),
    user_info: tuple = Depends(get_current_user_with_tenant),
    db: Session = Depends(get_session)
):
    """
    Train a new anomaly detection model.
    """
    user_id, tenant_id = user_info
    
    # Get file
    file = db.query(FileModel).filter(
        FileModel.id == file_id,
        FileModel.tenant_id == tenant_id
    ).first()
    
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    if file.status != "PROCESSED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be processed before training"
        )
    
    try:
        # Read file
        import json
        from pathlib import Path
        
        file_path = Path(file.storage_path)
        
        if file.file_type == ".csv":
            df = pd.read_csv(file_path)
        elif file.file_type in [".xlsx", ".xls"]:
            df = pd.read_excel(file_path)
        elif file.file_type == ".json":
            with open(file_path, 'r') as f:
                data = json.load(f)
            if isinstance(data, list):
                df = pd.DataFrame(data)
            else:
                df = pd.DataFrame([data])
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type: {file.file_type}"
            )
        
        # Analyze and extract features
        feature_extractor = FeatureExtractor()
        analysis = feature_extractor.analyze_data(df)
        features, feature_names = feature_extractor.extract_features(df, training=True)
        
        # Generate model name if not provided
        if not model_name:
            model_name = f"anomaly_model_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        # Create and train model
        model = model_manager.create_model(
            model_name=model_name,
            feature_names=feature_names,
            description=description
        )
        
        metrics = model_manager.train_model(
            model_name=model_name,
            X=features,
            feature_extractor=feature_extractor
        )
        
        # Initialize shadow mode if enabled
        shadow_info = None
        if config.shadow_mode_enabled:
            shadow_manager = model_manager.initialize_shadow_mode(model_name)
            shadow_metrics = model_manager.train_shadow_model(model_name, features)
            shadow_info = {
                "shadow_model_trained": True,
                "shadow_metrics": shadow_metrics
            }
        
        result = {
            "model_name": model_name,
            "training_metrics": metrics,
            "feature_analysis": analysis,
            "features_used": feature_names,
            "training_samples": len(df),
            "file_used": {
                "file_id": str(file_id),
                "filename": file.original_filename
            }
        }
        
        if shadow_info:
            result["shadow_mode"] = shadow_info
        
        logger.info(f"Trained anomaly model: {model_name}", tenant_id=str(tenant_id))
        
        return result
        
    except Exception as e:
        logger.error(f"Error training model: {str(e)}", tenant_id=str(tenant_id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model training failed: {str(e)}"
        )


@router.get("/models")
async def list_anomaly_models(
    user_info: tuple = Depends(get_current_user_with_tenant)
):
    """
    List available anomaly detection models.
    """
    user_id, tenant_id = user_info
    
    models = model_manager.list_models()
    
    return {
        "models": models,
        "total_models": len(models),
        "default_model": config.default_model
    }


@router.get("/models/{model_name}")
async def get_model_info(
    model_name: str,
    user_info: tuple = Depends(get_current_user_with_tenant)
):
    """
    Get information about a specific model.
    """
    user_id, tenant_id = user_info
    
    model_info = model_manager.get_model_info(model_name)
    
    if not model_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_name}' not found"
        )
    
    return model_info


@router.post("/models/{model_name}/explain")
async def explain_anomaly(
    model_name: str,
    features: Dict[str, float] = Body(...),
    top_n: int = Query(5, description="Number of top contributing features"),
    user_info: tuple = Depends(get_current_user_with_tenant)
):
    """
    Explain why a record was flagged as anomaly.
    """
    user_id, tenant_id = user_info
    
    model = model_manager.get_model(model_name)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_name}' not found"
        )
    
    if not model.is_trained:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Model '{model_name}' is not trained"
        )
    
    try:
        explanation = model.explain_anomaly(features, top_n=top_n)
        return explanation
        
    except Exception as e:
        logger.error(f"Error explaining anomaly: {str(e)}", tenant_id=str(tenant_id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Explanation failed: {str(e)}"
        )