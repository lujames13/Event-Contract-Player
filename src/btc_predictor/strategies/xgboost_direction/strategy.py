import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional
from btc_predictor.strategies.base import BaseStrategy
from btc_predictor.models import PredictionSignal
from btc_predictor.strategies.xgboost_direction.features import generate_features, get_feature_columns
from btc_predictor.strategies.xgboost_direction.model import predict_higher_probability, load_model

class XGBoostDirectionStrategy(BaseStrategy):
    def __init__(self, model_path: Optional[str] = None, model=None):
        self._name = "xgboost_v1"
        self.model = model
        if model_path:
            self.model = load_model(model_path)

    @property
    def name(self) -> str:
        return self._name

    def predict(
        self,
        ohlcv: pd.DataFrame,
        timeframe_minutes: int,
    ) -> PredictionSignal:
        """
        Generate prediction signal using the XGBoost model.
        
        Args:
            ohlcv: DataFrame with columns: open, high, low, close, volume.
            timeframe_minutes: The prediction horizon.
            
        Returns:
            PredictionSignal.
        """
        if self.model is None:
            raise ValueError("Model not loaded for XGBoostDirectionStrategy")
            
        # 1. Generate features
        feat_df = generate_features(ohlcv)
        
        # 2. Get the last row (latest data)
        latest_features = feat_df.iloc[[-1]]
        
        # 3. Select relevant feature columns
        feature_cols = get_feature_columns()
        X = latest_features[feature_cols]
        
        # 4. Predict probability
        prob_higher = predict_higher_probability(self.model, X)[0]
        
        # 5. Determine direction and confidence
        if prob_higher > 0.5:
            direction = "higher"
            confidence = prob_higher
        else:
            direction = "lower"
            confidence = 1.0 - prob_higher
            
        # 6. Construct PredictionSignal
        current_price = ohlcv['close'].iloc[-1]
        
        # Optionally extract top features for features_used dict (SHAP etc in Phase 2)
        # For now, just a placeholder or empty
        features_used = {} 
        
        return PredictionSignal(
            strategy_name=self.name,
            timestamp=datetime.now(), # In production, this might be the candle close time
            timeframe_minutes=timeframe_minutes, # type: ignore
            direction=direction, # type: ignore
            confidence=float(confidence),
            current_price=float(current_price),
            features_used=features_used
        )
