import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional
from pathlib import Path
from btc_predictor.strategies.base import BaseStrategy
from btc_predictor.models import PredictionSignal
from btc_predictor.strategies.lgbm_v1.features import generate_features, get_feature_columns
from btc_predictor.strategies.lgbm_v1.model import predict_higher_probability, load_model, train_model
from btc_predictor.infrastructure.labeling import add_direction_labels

class LGBMDirectionStrategy(BaseStrategy):
    def __init__(self, model_path: Optional[str] = None):
        self._name = "lgbm_v1"
        self.models = {}  # timeframe -> model
        
        if model_path:
            p = Path(model_path)
            # If path is a directory, load all models
            if p.is_dir():
                self.load_models_from_dir(p)
            else:
                # Specific file, assume 10m if not specified in name
                stem = p.stem
                if stem.endswith("m") and stem[:-1].isdigit():
                    tf = int(stem[:-1])
                else:
                    tf = 10
                self.models[tf] = load_model(model_path)

    @property
    def name(self) -> str:
        return self._name

    @property
    def requires_fitting(self) -> bool:
        return True
        
    def load_models_from_dir(self, models_dir: Path):
        if not models_dir.exists():
            return
        for file_path in models_dir.glob("*.pkl"):
            stem = file_path.stem
            if stem.endswith("m") and stem[:-1].isdigit():
                tf = int(stem[:-1])
                try:
                    self.models[tf] = load_model(str(file_path))
                except Exception as e:
                    print(f"Failed to load model {file_path}: {e}")

    def fit(self, ohlcv: pd.DataFrame, timeframe_minutes: int) -> None:
        feat_df = generate_features(ohlcv)
        labeled_df = add_direction_labels(feat_df, timeframe_minutes)
        feature_cols = get_feature_columns()
        labeled_df = labeled_df.dropna(subset=["label"] + feature_cols)
        
        if labeled_df.empty:
            raise ValueError("No training samples")
            
        # Initial LightGBM will also use validation split for early stopping
        val_size = int(len(labeled_df) * 0.2)
        train_size = len(labeled_df) - val_size
        gap_rows = 1 # One candle gap is enough if labeled properly
        
        train_end = train_size - gap_rows
        if train_end <= 0:
            train_idx = labeled_df.iloc[:train_size]
            val_idx = labeled_df.iloc[train_size:]
        else:
            train_idx = labeled_df.iloc[:train_end]
            val_idx = labeled_df.iloc[train_size:]
            
        X_train = train_idx[feature_cols]
        y_train = train_idx["label"]
        X_val = val_idx[feature_cols]
        y_val = val_idx["label"]
        
        self.models[timeframe_minutes] = train_model(X_train, y_train, val_data=(X_val, y_val))

    def predict(self, ohlcv: pd.DataFrame, timeframe_minutes: int) -> PredictionSignal:
        model = self.models.get(timeframe_minutes)
        if model is None:
            raise ValueError(f"Model not trained for timeframe {timeframe_minutes}")
            
        feat_df = generate_features(ohlcv)
        latest_features = feat_df.iloc[[-1]]
        feature_cols = get_feature_columns()
        X = latest_features[feature_cols]
        
        prob_higher = predict_higher_probability(model, X)[0]
        
        if prob_higher > 0.5:
            direction = "higher"
            confidence = prob_higher
        else:
            direction = "lower"
            confidence = 1.0 - prob_higher
            
        return PredictionSignal(
            strategy_name=self.name,
            timestamp=ohlcv.index[-1],
            timeframe_minutes=timeframe_minutes,
            direction=direction,
            confidence=float(confidence),
            current_price=float(ohlcv['close'].iloc[-1]),
            features_used={}
        )
