import lightgbm as lgb
import pandas as pd
import numpy as np
import pickle
from pathlib import Path
from typing import Optional, Dict, Any

def train_model(
    X: pd.DataFrame, 
    y: pd.Series, 
    params: Optional[Dict[str, Any]] = None,
    val_data: Optional[tuple] = None
) -> lgb.LGBMClassifier:
    """
    Train a LightGBM classifier for direction prediction.
    """
    default_params = {
        'n_estimators': 500,
        'learning_rate': 0.05,
        'num_leaves': 31,
        'objective': 'binary',
        'random_state': 42,
        'n_jobs': 1,
        'importance_type': 'split',
        'verbose': -1
    }
    
    if params:
        default_params.update(params)
    
    early_stop = default_params.pop('early_stopping_rounds', 50)
    model = lgb.LGBMClassifier(**default_params)
    
    if val_data:
        X_val, y_val = val_data
        model.fit(
            X, y,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(stopping_rounds=early_stop)]
        )
    else:
        model.fit(X, y)
        
    return model

def predict_higher_probability(model: lgb.LGBMClassifier, X: pd.DataFrame) -> np.ndarray:
    """
    Predict the probability of the 'higher' (label 1) outcome.
    """
    # [prob_0, prob_1]
    return model.predict_proba(X)[:, 1]

def save_model(model: lgb.LGBMClassifier, path: str):
    """Save the model to a file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'wb') as f:
        pickle.dump(model, f)

def load_model(path: str) -> lgb.LGBMClassifier:
    """Load the model from a file."""
    with open(path, 'rb') as f:
        return pickle.load(f)
