import logging
import pandas as pd
import numpy as np
from typing import Optional, List
from pathlib import Path
from btc_predictor.strategies.base import BaseStrategy
from btc_predictor.models import PredictionSignal
from btc_predictor.infrastructure.labeling import add_regression_labels
from btc_predictor.strategies.pm_lgbm_reg_v1.model import train_model, load_model, save_model
from btc_predictor.strategies.pm_common.features_short import generate_features, get_feature_columns

logger = logging.getLogger(__name__)

class PMLGBMRegV1Strategy(BaseStrategy):
    def __init__(self, model_path: Optional[str] = None, model=None):
        self._name = "pm_lgbm_reg_v1"
        self.models = {}
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
        for file_path in models_dir.glob("*.txt"):
            stem = file_path.stem
            if stem.endswith("m") and stem[:-1].isdigit():
                tf = int(stem[:-1])
                try:
                    self.models[tf] = load_model(str(file_path))
                    logger.info(f"Loaded {self._name} model for {tf}m")
                except Exception as e:
                    logger.error(f"Failed to load {self._name} model {file_path}: {e}")

    def save_model(self, timeframe: int, path: str):
        model = self.models.get(timeframe)
        if model:
            if not path.endswith(".txt"):
                path = path.replace(".pkl", ".txt")
            save_model(model, path)

    def fit(self, ohlcv: pd.DataFrame, timeframe_minutes: int) -> None:
        feat_df = generate_features(ohlcv)
        labeled_df = add_regression_labels(feat_df, timeframe_minutes)
        feature_cols = get_feature_columns()
        
        data = labeled_df.dropna(subset=['price_change_pct'] + feature_cols)
        if len(data) < 100:
            raise ValueError(f"Insufficient samples for training ({len(data)})")
            
        X = data[feature_cols]
        y = data['price_change_pct'] * 100.0
        self.models[timeframe_minutes] = train_model(X, y)

    def predict(self, ohlcv: pd.DataFrame, timeframe_minutes: int) -> PredictionSignal:
        model = self.models.get(timeframe_minutes)
        if model is None:
            raise ValueError(f"Model not trained for {timeframe_minutes}m")
            
        feat_df = generate_features(ohlcv.iloc[-100:])
        X = feat_df[get_feature_columns()].iloc[[-1]]
        predicted_change = model.predict(X)[0] / 100.0
        
        direction = "higher" if predicted_change > 0 else "lower"
        confidence = float(abs(predicted_change))
        
        return PredictionSignal(
            strategy_name=self.name,
            timestamp=ohlcv.index[-1],
            timeframe_minutes=timeframe_minutes,
            direction=direction,
            confidence=confidence,
            current_price=float(ohlcv['close'].iloc[-1]),
            features_used=get_feature_columns(),
            market_slug=f"btc-price-at-{ohlcv.index[-1].strftime('%Y%m%d%H%M')}-{timeframe_minutes}m",
            market_price_up=0.5,
            alpha=float(predicted_change)
        )
