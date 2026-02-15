import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, List
from pathlib import Path
from btc_predictor.strategies.base import BaseStrategy
from btc_predictor.models import PredictionSignal
from btc_predictor.strategies.catboost_v1.features import generate_features, get_feature_columns
from btc_predictor.strategies.catboost_v1.model import train_model, load_model, save_model
from btc_predictor.data.labeling import add_direction_labels

class CatBoostDirectionStrategy(BaseStrategy):
    """
    CatBoost Strategy:
    - Uses CatBoost for direction classification.
    - Standard features.
    - Early stopping with validation set.
    """
    def __init__(self, model_path: Optional[str] = None, model=None):
        self._name = "catboost_v1"
        self.models = {}  # timeframe -> model
        
        if model:
            self.models[10] = model # Default for testing
            
        if model_path:
            p = Path(model_path)
            if p.is_dir():
                self.load_models_from_dir(p)

    @property
    def name(self) -> str:
        return self._name

    @property
    def requires_fitting(self) -> bool:
        return True
        
    def load_models_from_dir(self, models_dir: Path):
        for file_path in models_dir.glob("catboost_v1_*.cbm"):
            stem = file_path.stem
            # Expected name: catboost_v1_10m.cbm
            parts = stem.split("_")
            if len(parts) >= 3 and parts[-1].endswith("m"):
                tf_part = parts[-1][:-1]
                if tf_part.isdigit():
                    tf = int(tf_part)
                    try:
                        self.models[tf] = load_model(str(file_path))
                        print(f"Loaded CatBoost model for {tf}m")
                    except Exception as e:
                        print(f"Failed to load model {file_path}: {e}")

    def save_model(self, timeframe: int, path: str):
        model = self.models.get(timeframe)
        if model:
            # Standardize extension
            if not path.endswith(".cbm"):
                path = path.replace(".pkl", ".cbm")
            save_model(model, path)

    def fit(self, ohlcv: pd.DataFrame, timeframe_minutes: int) -> None:
        feat_df = generate_features(ohlcv)
        labeled_df = add_direction_labels(feat_df, timeframe_minutes)
        feature_cols = get_feature_columns()
        
        # Drop rows with NaNs
        data = labeled_df.dropna(subset=['label'] + feature_cols)
        
        if len(data) < 100:
            raise ValueError(f"Insufficient samples for training ({len(data)})")
            
        # Validation split (last 20%)
        val_size = int(len(data) * 0.2)
        train_df = data.iloc[:-val_size]
        val_df = data.iloc[-val_size:]
        
        X_train = train_df[feature_cols]
        y_train = train_df['label']
        X_val = val_df[feature_cols]
        y_val = val_df['label']
        
        self.models[timeframe_minutes] = train_model(
            X_train, y_train, 
            val_data=(X_val, y_val)
        )

    def predict(self, ohlcv: pd.DataFrame, timeframe_minutes: int) -> PredictionSignal:
        model = self.models.get(timeframe_minutes)
        if model is None:
            raise ValueError(f"Model not trained for {timeframe_minutes}m")
            
        feat_df = generate_features(ohlcv)
        # Squeeze to get last row as 2D array
        latest_features = feat_df.iloc[[-1]] 
        X = latest_features[get_feature_columns()]
        
        # predict_proba returns [prob_0, prob_1]
        probs = model.predict_proba(X)[0]
        prob_higher = probs[1]
        
        if prob_higher > 0.5:
            direction = "higher"
            confidence = prob_higher
        else:
            direction = "lower"
            confidence = 1.0 - prob_higher
            
        return PredictionSignal(
            strategy_name=self.name,
            timestamp=ohlcv.index[-1],
            timeframe_minutes=timeframe_minutes, # type: ignore
            direction=direction,
            confidence=float(confidence),
            current_price=float(ohlcv['close'].iloc[-1]),
            features_used={}
        )
