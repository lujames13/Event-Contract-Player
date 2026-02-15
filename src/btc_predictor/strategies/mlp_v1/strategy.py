import pandas as pd
import torch
from typing import Optional
from pathlib import Path
from btc_predictor.strategies.base import BaseStrategy
from btc_predictor.models import PredictionSignal
from btc_predictor.strategies.mlp_v1.features import generate_features, get_feature_columns
from btc_predictor.strategies.mlp_v1.model import train_mlp, load_model, save_model, MLP
from btc_predictor.data.labeling import add_direction_labels

class MLPStrategy(BaseStrategy):
    def __init__(self, model_path: Optional[str] = None):
        self._name = "mlp_v1"
        self.models = {}  # timeframe -> model
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        if model_path:
            p = Path(model_path)
            if p.is_dir():
                self.load_models_from_dir(p)
            else:
                # Need input_dim to load MLP
                # This is a limitation of the current BaseStrategy interface if loading directly from file
                # But Registry usually passes the directory.
                pass

    @property
    def name(self) -> str:
        return self._name

    @property
    def requires_fitting(self) -> bool:
        return True
        
    def load_models_from_dir(self, models_dir: Path):
        if not models_dir.exists():
            return
        feature_cols = get_feature_columns()
        input_dim = len(feature_cols)
        
        for file_path in models_dir.glob("*.*"):
            if file_path.suffix not in [".pkl", ".pth"]: continue
            stem = file_path.stem
            if stem.endswith("m") and stem[:-1].isdigit():
                tf = int(stem[:-1])
                try:
                    self.models[tf] = load_model(str(file_path), input_dim, self.device)
                except Exception as e:
                    print(f"Failed to load MLP model {file_path}: {e}")

    def save_model(self, timeframe: int, path: str):
        """Save the model for a specific timeframe to path."""
        model = self.models.get(timeframe)
        if model is None:
            raise ValueError(f"No model found for timeframe {timeframe}")
        
        # Standardize on .pkl for consistency with training scripts
        if not (path.endswith(".pkl") or path.endswith(".pth")):
            path = str(Path(path).with_suffix(".pkl"))
            
        from btc_predictor.strategies.mlp_v1.model import save_model as _save_impl
        _save_impl(model, path)

    def fit(self, ohlcv: pd.DataFrame, timeframe_minutes: int) -> None:
        feat_df = generate_features(ohlcv)
        labeled_df = add_direction_labels(feat_df, timeframe_minutes)
        feature_cols = get_feature_columns()
        
        # Drop rows with NaNs (from features, labels, and rolling windows)
        data = labeled_df.dropna(subset=['label'] + feature_cols)
        
        if len(data) < 100:
            raise ValueError(f"Insufficient samples for training ({len(data)})")

        # Walk-forward like split (last 20% for val)
        val_size = int(len(data) * 0.2)
        train_df = data.iloc[:-val_size]
        val_df = data.iloc[-val_size:]
        
        X_train = train_df[feature_cols]
        y_train = train_df['label']
        X_val = val_df[feature_cols]
        y_val = val_df['label']
        
        print(f"[{self.name}] Training MLP on {len(X_train)} samples...")
        self.models[timeframe_minutes] = train_mlp(
            X_train, y_train, 
            val_data=(X_val, y_val),
            device=str(self.device)
        )

    def predict(self, ohlcv: pd.DataFrame, timeframe_minutes: int) -> PredictionSignal:
        model = self.models.get(timeframe_minutes)
        if model is None:
            raise ValueError(f"Model not trained for timeframe {timeframe_minutes}")
            
        feat_df = generate_features(ohlcv)
        latest_features = feat_df.iloc[[-1]]
        feature_cols = get_feature_columns()
        
        # If we have NaNs in the latest features (e.g. not enough data for 60-period rolling z-score)
        # we might need to handle it.
        X_df = latest_features[feature_cols]
        if X_df.isnull().any().any():
            # For inference, if we have NaNs, we can't make a good prediction.
            # But during live it should have enough history.
            # Here we just fill with 0 as a fallback (z-score 0 = mean).
            X_df = X_df.fillna(0)
            
        X = torch.tensor(X_df.values, dtype=torch.float32).to(self.device)
        
        model.eval()
        with torch.no_grad():
            prob_higher = model(X).item()
        
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
