import xgboost as xgb
import pandas as pd
import numpy as np
import pickle
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from btc_predictor.strategies.xgboost_v1.features import generate_features, get_feature_columns
from btc_predictor.data.labeling import add_direction_labels

def train_model(
    X: pd.DataFrame, 
    y: pd.Series, 
    params: Optional[Dict[str, Any]] = None,
    val_data: Optional[tuple] = None
) -> xgb.XGBClassifier:
    """
    Train an XGBoost classifier for direction prediction.
    
    Args:
        X: Training features.
        y: Training labels (0 or 1).
        params: Optional hyperparameters.
        val_data: Optional tuple of (X_val, y_val) for early stopping.
        
    Returns:
        Trained XGBClassifier.
    """
    default_params = {
        'max_depth': 6,
        'n_estimators': 500,
        'learning_rate': 0.05,
        'objective': 'binary:logistic',
        'random_state': 42,
        'n_jobs': 1,
        'eval_metric': 'logloss'
    }
    
    if params:
        default_params.update(params)
        
    # Handle class imbalance if needed (scale_pos_weight)
    if 'scale_pos_weight' not in default_params:
        num_pos = (y == 1).sum()
        num_neg = (y == 0).sum()
        if num_pos > 0:
            default_params['scale_pos_weight'] = num_neg / num_pos
            
    if val_data:
        default_params['early_stopping_rounds'] = 50
        
    model = xgb.XGBClassifier(**default_params)
    
    if val_data:
        X_val, y_val = val_data
        model.fit(
            X, y,
            eval_set=[(X_val, y_val)],
            verbose=False
        )
    else:
        model.fit(X, y)
        
    return model

def predict_higher_probability(model: xgb.XGBClassifier, X: pd.DataFrame) -> np.ndarray:
    """
    Predict the probability of the 'higher' (label 1) outcome.
    
    Returns:
        Numpy array of probabilities.
    """
    # model.predict_proba returns [prob_0, prob_1]
    return model.predict_proba(X)[:, 1]

def save_model(model: xgb.XGBClassifier, path: str):
    """Save the model to a file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'wb') as f:
        pickle.dump(model, f)

def load_model(path: str) -> xgb.XGBClassifier:
    """Load the model from a file."""
    with open(path, 'rb') as f:
        return pickle.load(f)

class XGBoostDirectionModel:
    """
    Wrapper class for XGBoost direction prediction model.
    Encapsulates feature generation, labeling, training, and prediction.
    """
    def __init__(self, model_path: Optional[str] = None):
        self.model = None
        if model_path:
            self.load(model_path)
            
    def fit(self, ohlcv: pd.DataFrame, timeframe_minutes: int, params: Optional[Dict[str, Any]] = None) -> float:
        """
        Train the model and return training accuracy.
        """
        # 1. Generate features
        feat_df = generate_features(ohlcv)
        
        # 2. Add labels
        labeled_df = add_direction_labels(feat_df, timeframe_minutes)
        
        # 3. Clean NaN
        feature_cols = get_feature_columns()
        labeled_df = labeled_df.dropna(subset=["label"] + feature_cols)
        
        if labeled_df.empty:
            raise ValueError("No valid training samples")
            
        # 4. Extract X and y
        X = labeled_df[feature_cols]
        y = labeled_df["label"]
        
        # 5. Train
        self.model = train_model(X, y, params)
        
        # 6. Calculate accuracy
        y_pred = self.model.predict(X)
        accuracy = (y_pred == y).mean()
        
        return accuracy
    
    def predict_proba(self, ohlcv: pd.DataFrame) -> float:
        """
        Predict probability of price going higher based on the latest data point.
        """
        if self.model is None:
            raise ValueError("Model not trained or loaded")
            
        # 1. Generate features
        feat_df = generate_features(ohlcv)
        
        # 2. Get latest features
        latest_features = feat_df.iloc[[-1]]
        feature_cols = get_feature_columns()
        X = latest_features[feature_cols]
        
        # 3. Predict
        prob_higher = predict_higher_probability(self.model, X)[0]
        
        return float(prob_higher)
        
    def save(self, path: str):
        if self.model is None:
            raise ValueError("No model to save")
        save_model(self.model, path)
        
    def load(self, path: str):
        self.model = load_model(path)
