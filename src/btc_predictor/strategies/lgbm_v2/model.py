import lightgbm as lgb
import pandas as pd
import numpy as np
import pickle
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from sklearn.isotonic import IsotonicRegression

def train_model_with_calibration(
    X: pd.DataFrame, 
    y: pd.Series, 
    params: Optional[Dict[str, Any]] = None,
    val_data: Optional[Tuple[pd.DataFrame, pd.Series]] = None
) -> Tuple[lgb.LGBMClassifier, Optional[IsotonicRegression]]:
    """
    Train a LightGBM classifier and calibrate probabilities using Isotonic Regression.
    """
    default_params = {
        'n_estimators': 500,
        'learning_rate': 0.05,
        'num_leaves': 31,
        'objective': 'binary',
        'random_state': 42,
        'n_jobs': 1,
        'verbose': -1
    }
    
    if params:
        default_params.update(params)
        
    model = lgb.LGBMClassifier(**default_params)
    
    if val_data:
        X_val, y_val = val_data
        model.fit(
            X, y,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(stopping_rounds=50)]
        )
        
        # Calibration using validation set
        val_probs = model.predict_proba(X_val)[:, 1]
        iso_reg = IsotonicRegression(out_of_bounds='clip')
        iso_reg.fit(val_probs, y_val)
        
        return model, iso_reg
    else:
        model.fit(X, y)
        return model, None

def save_calibrated_model(model: lgb.LGBMClassifier, iso_reg: Optional[IsotonicRegression], path: str):
    """Save the model and calibrator to a file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'wb') as f:
        pickle.dump({'model': model, 'iso_reg': iso_reg}, f)

def load_calibrated_model(path: str) -> Tuple[lgb.LGBMClassifier, Optional[IsotonicRegression]]:
    """Load the model and calibrator from a file."""
    with open(path, 'rb') as f:
        data = pickle.load(f)
        if isinstance(data, dict):
            return data['model'], data['iso_reg']
        else:
            # Fallback for old version
            return data, None
