import catboost as cb
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
) -> cb.CatBoostClassifier:
    """
    Train a CatBoost classifier for direction prediction.
    """
    default_params = {
        'iterations': 500,
        'learning_rate': 0.05,
        'depth': 6,
        'loss_function': 'Logloss',
        'random_seed': 42,
        'verbose': False,
        'allow_writing_files': False,
        'thread_count': 1 # For parallel backtesting compatibility
    }
    
    if params:
        default_params.update(params)
        
    model = cb.CatBoostClassifier(**default_params)
    
    if val_data:
        X_val, y_val = val_data
        model.fit(
            X, y,
            eval_set=(X_val, y_val),
            early_stopping_rounds=50
        )
    else:
        model.fit(X, y)
        
    return model

def save_model(model: cb.CatBoostClassifier, path: str):
    """Save the model to a file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(path), format="cbm")

def load_model(path: str) -> cb.CatBoostClassifier:
    """Load the model from a file."""
    model = cb.CatBoostClassifier()
    model.load_model(str(path), format="cbm")
    return model
