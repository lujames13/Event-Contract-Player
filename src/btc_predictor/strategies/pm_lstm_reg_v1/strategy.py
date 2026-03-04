import logging
import pandas as pd
import numpy as np
from typing import Optional, List
from pathlib import Path
from btc_predictor.strategies.base import BaseStrategy
from btc_predictor.models import PredictionSignal
from btc_predictor.infrastructure.labeling import add_regression_labels
from btc_predictor.strategies.pm_lstm_reg_v1.model import train_model, load_model, save_model
from btc_predictor.strategies.pm_common.features_window import generate_window_features, get_window_columns

logger = logging.getLogger(__name__)

class PMLSTMRegV1Strategy(BaseStrategy):
    def __init__(self, model_path: Optional[str] = None, model=None):
        self._name = "pm_lstm_reg_v1"
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
        for file_path in models_dir.glob("*.pt"):
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
            if not path.endswith(".pt"):
                path = path.replace(".pkl", ".pt")
            save_model(model, path)

    def fit(self, ohlcv: pd.DataFrame, timeframe_minutes: int) -> None:
        X, valid_indices = generate_window_features(ohlcv)
        if len(X) == 0:
            raise ValueError("Insufficient data to generate windows.")
            
        # Align labels
        labeled_df = add_regression_labels(ohlcv, timeframe_minutes)
        y_all = labeled_df.loc[valid_indices, 'price_change_pct'].values * 100.0
        
        # Valid pairs
        valid_mask = ~np.isnan(y_all)
        X_clean = X[valid_mask]
        y_clean = y_all[valid_mask]
        
        if len(X_clean) < 100:
            raise ValueError(f"Insufficient samples for training ({len(X_clean)})")
            
        val_size = max(1, int(len(X_clean) * 0.2))
        X_train, y_train = X_clean[:-val_size], y_clean[:-val_size]
        X_val, y_val = X_clean[-val_size:], y_clean[-val_size:]
        self.models[timeframe_minutes] = train_model(X_train, y_train, (X_val, y_val))

    def predict(self, ohlcv: pd.DataFrame, timeframe_minutes: int) -> PredictionSignal:
        model = self.models.get(timeframe_minutes)
        if model is None:
            raise ValueError(f"Model not trained for {timeframe_minutes}m")
            
        # Generate single window for prediction
        # To just get last window, pass last 30 rows
        X, _ = generate_window_features(ohlcv.iloc[-100:])
        if len(X) == 0:
            raise ValueError("Insufficient data for inference window.")
        predicted_change = model.predict(X[-1:])[0] / 100.0
        
        direction = "higher" if predicted_change > 0 else "lower"
        confidence = float(abs(predicted_change))
        
        return PredictionSignal(
            strategy_name=self.name,
            timestamp=ohlcv.index[-1],
            timeframe_minutes=timeframe_minutes,
            direction=direction,
            confidence=confidence,
            current_price=float(ohlcv['close'].iloc[-1]),
            features_used=get_window_columns(),
            market_slug=f"btc-price-at-{ohlcv.index[-1].strftime('%Y%m%d%H%M')}-{timeframe_minutes}m",
            market_price_up=0.5,
            alpha=float(predicted_change)
        )
