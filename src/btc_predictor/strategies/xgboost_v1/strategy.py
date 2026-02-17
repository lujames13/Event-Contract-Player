import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional
from pathlib import Path
from btc_predictor.strategies.base import BaseStrategy
from btc_predictor.models import PredictionSignal
from btc_predictor.strategies.xgboost_v1.features import generate_features, get_feature_columns
from btc_predictor.strategies.xgboost_v1.model import predict_higher_probability, load_model, train_model
from btc_predictor.data.labeling import add_direction_labels

class XGBoostDirectionStrategy(BaseStrategy):
    def __init__(self, model_path: Optional[str] = None, model=None):
        self._name = "xgboost_v1"
        self.models = {}  # timeframe -> model
        
        # Backward compatibility for single model loading
        if model_path:
            # Try to infer timeframe from filename, default to 10m if not found
            # e.g. "models/xgboost_v1/30m.pkl" -> 30
            try:
                p = Path(model_path)
                stem = p.stem  # "30m"
                if stem.endswith("m") and stem[:-1].isdigit():
                    tf = int(stem[:-1])
                else:
                    tf = 10
                self.models[tf] = load_model(model_path)
            except Exception:
                # Fallback
                self.models[10] = load_model(model_path)
                
        if model:
            # Assume 10m for passed model object if no context
            self.models[10] = model

    @property
    def name(self) -> str:
        return self._name

    @property
    def requires_fitting(self) -> bool:
        return True
        
    @property
    def available_timeframes(self) -> list[int]:
        return list(self.models.keys())
        
    def load_models_from_dir(self, models_dir: Path):
        """Load all .pkl files from the directory as models."""
        if not models_dir.exists():
            return
            
        for file_path in models_dir.glob("*.pkl"):
            stem = file_path.stem  # e.g. "10m"
            if stem.endswith("m") and stem[:-1].isdigit():
                tf = int(stem[:-1])
                try:
                    self.models[tf] = load_model(str(file_path))
                except Exception as e:
                    print(f"Failed to load model {file_path}: {e}")

    def save_model(self, timeframe: int, path: str):
        """Save the model for a specific timeframe to path."""
        model = self.models.get(timeframe)
        if model is None:
            raise ValueError(f"No model found for timeframe {timeframe}")
        
        # Import save_model from model.py
        from btc_predictor.strategies.xgboost_v1.model import save_model as _save_impl
        _save_impl(model, path)


    def fit(
        self,
        ohlcv: pd.DataFrame,
        timeframe_minutes: int,
    ) -> None:
        """
        Train the XGBoost model using the provided data.
        """
        # 1. Generate features
        feat_df = generate_features(ohlcv)
        
        # 2. Add labels
        labeled_df = add_direction_labels(feat_df, timeframe_minutes)
        
        # 3. Clean NaN (caused by features or end-of-data labels)
        labeled_df = labeled_df.dropna(subset=["label"] + get_feature_columns())
        
        if labeled_df.empty:
            raise ValueError("No valid training samples after feature generation and labeling")
            
        # 4. Extract X and y
        feature_cols = get_feature_columns()
        X = labeled_df[feature_cols]
        y = labeled_df["label"]
        
        # 5. Train model
        model = train_model(X, y)
        self.models[timeframe_minutes] = model

    def predict(
        self,
        ohlcv: pd.DataFrame,
        timeframe_minutes: int,
    ) -> PredictionSignal:
        """
        Generate prediction signal using the XGBoost model.
        """
        model = self.models.get(timeframe_minutes)
        if model is None:
            # If no model for this timeframe, maybe we should return a neutral signal?
            # Or raise error? The spec says "un-trained strategies don't participate".
            # But here `predict` is called, so it expects a signal.
            # BaseStrategy interface doesn't define error behavior clearly.
            # But the caller (engine) expects PredictionSignal.
            # Let's raise an error or return neutral.
            # Raising error is safer to detect issues.
            raise ValueError(f"Model not loaded/trained for XGBoostDirectionStrategy timeframe {timeframe_minutes}")
            
        # 1. Generate features
        feat_df = generate_features(ohlcv)
        
        # 2. Get the last row (latest data)
        latest_features = feat_df.iloc[[-1]]
        
        # 3. Select relevant feature columns
        feature_cols = get_feature_columns()
        X = latest_features[feature_cols]
        
        # 4. Predict probability
        prob_higher = predict_higher_probability(model, X)[0]
        
        # 5. Determine direction and confidence
        if prob_higher > 0.5:
            direction = "higher"
            confidence = prob_higher
        else:
            direction = "lower"
            confidence = 1.0 - prob_higher
            
        # 6. Construct PredictionSignal
        current_price = ohlcv['close'].iloc[-1]
        
        # Use the actual timestamp from the last OHLCV row if available
        timestamp = ohlcv.index[-1] if isinstance(ohlcv.index, pd.DatetimeIndex) else datetime.now()
        
        features_used = {} 
        
        return PredictionSignal(
            strategy_name=self.name,
            timestamp=timestamp, # type: ignore
            timeframe_minutes=timeframe_minutes, # type: ignore
            direction=direction, # type: ignore
            confidence=float(confidence),
            current_price=float(current_price),
            features_used=features_used
        )
