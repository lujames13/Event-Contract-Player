import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, List
from pathlib import Path
from btc_predictor.strategies.base import BaseStrategy
from btc_predictor.models import PredictionSignal
from btc_predictor.strategies.lgbm_v2.features import generate_features, get_feature_columns
from btc_predictor.strategies.lgbm_v2.model import train_model_with_calibration, load_calibrated_model, save_calibrated_model
from btc_predictor.data.labeling import add_direction_labels

class LGBMDirectionStrategyV2(BaseStrategy):
    """
    LightGBM Strategy V2:
    - Expanded data (180 days training)
    - Feature selection (Top 20 based on Gain)
    - Early Stopping with Purged Validation Gap
    - Probability Calibration via Isotonic Regression
    """
    def __init__(self, model_path: Optional[str] = None):
        self._name = "lgbm_v2"
        self.models = {}      # timeframe -> model
        self.calibrators = {} # timeframe -> iso_reg
        
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

    @property
    def available_timeframes(self) -> List[int]:
        return list(self.models.keys())
        
    def load_models_from_dir(self, models_dir: Path):
        for file_path in models_dir.glob("*.pkl"):
            stem = file_path.stem
            if stem.endswith("m") and stem[:-1].isdigit():
                tf = int(stem[:-1])
                try:
                    model, iso_reg = load_calibrated_model(str(file_path))
                    self.models[tf] = model
                    self.calibrators[tf] = iso_reg
                except Exception as e:
                    print(f"Failed to load model {file_path}: {e}")

    def save_model(self, timeframe: int, path: str):
        model = self.models.get(timeframe)
        iso_reg = self.calibrators.get(timeframe)
        if model:
            save_calibrated_model(model, iso_reg, path)

    def fit(self, ohlcv: pd.DataFrame, timeframe_minutes: int) -> None:
        # 1. Generate features
        feat_df = generate_features(ohlcv)
        
        # 2. Add labels
        labeled_df = add_direction_labels(feat_df, timeframe_minutes)
        
        # 3. Use restricted feature set (Phase 2 Feature Selection)
        feature_cols = get_feature_columns()
        labeled_df = labeled_df.dropna(subset=["label"] + feature_cols)
        
        if labeled_df.empty:
            raise ValueError(f"No training samples for tf {timeframe_minutes}")
            
        # 4. Validation split (last 20%) with purged gap
        val_size = int(len(labeled_df) * 0.2)
        train_size = len(labeled_df) - val_size
        
        # Gap should be at least timeframe_minutes rows
        # Since ohlcv is 1m, gap_rows = timeframe_minutes
        gap_rows = timeframe_minutes
        
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
        
        # 5. Train with calibration
        model, iso_reg = train_model_with_calibration(X_train, y_train, val_data=(X_val, y_val))
        self.models[timeframe_minutes] = model
        self.calibrators[timeframe_minutes] = iso_reg

    def predict(self, ohlcv: pd.DataFrame, timeframe_minutes: int) -> PredictionSignal:
        model = self.models.get(timeframe_minutes)
        if model is None:
            raise ValueError(f"Model not trained for {timeframe_minutes}m")
            
        feat_df = generate_features(ohlcv)
        latest_features = feat_df.iloc[[-1]]
        X = latest_features[get_feature_columns()]
        
        # Raw probability
        prob_higher = model.predict_proba(X)[0, 1]
        
        # Calibrate if calibrator exists
        iso_reg = self.calibrators.get(timeframe_minutes)
        if iso_reg:
            # Isotonic regression expects 1D array
            prob_higher = iso_reg.transform([prob_higher])[0]
        
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
