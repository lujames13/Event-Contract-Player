import logging
import pandas as pd
from typing import Optional, List
from pathlib import Path
from btc_predictor.strategies.base import BaseStrategy
from btc_predictor.models import PredictionSignal
from btc_predictor.strategies.pm_v1.features import generate_features, get_feature_columns
from btc_predictor.strategies.pm_v1.model import train_model, load_model, save_model
from btc_predictor.infrastructure.labeling import add_direction_labels

logger = logging.getLogger(__name__)

class PMV1Strategy(BaseStrategy):
    """
    Polymarket v1 Strategy:
    - Uses CatBoost for direction classification.
    - Uses ">=" settlement condition for training.
    """
    def __init__(self, model_path: Optional[str] = None, model=None):
        self._name = "pm_v1"
        self.models = {}  # timeframe -> model
        
        if model:
            self.models[10] = model
            
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
        for file_path in models_dir.glob("*.cbm"):
            stem = file_path.stem
            if stem.endswith("m") and stem[:-1].isdigit():
                tf = int(stem[:-1])
                try:
                    self.models[tf] = load_model(str(file_path))
                    logger.info(f"Loaded pm_v1 model for {tf}m")
                except Exception as e:
                    logger.error(f"Failed to load pm_v1 model {file_path}: {e}")

    def save_model(self, timeframe: int, path: str):
        model = self.models.get(timeframe)
        if model:
            if not path.endswith(".cbm"):
                path = path.replace(".pkl", ".cbm")
            save_model(model, path)

    def fit(self, ohlcv: pd.DataFrame, timeframe_minutes: int) -> None:
        feat_df = generate_features(ohlcv)
        # Use >= settlement condition for Polymarket
        labeled_df = add_direction_labels(feat_df, timeframe_minutes, settlement_condition=">=")
        feature_cols = get_feature_columns()
        
        data = labeled_df.dropna(subset=['label'] + feature_cols)
        
        if len(data) < 100:
            raise ValueError(f"Insufficient samples for training ({len(data)})")
            
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
        latest_features = feat_df.iloc[[-1]] 
        X = latest_features[get_feature_columns()]
        
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
