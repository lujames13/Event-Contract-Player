import xgboost as xgb
from typing import Tuple
import pandas as pd

def train_model(X_train: pd.DataFrame, y_train: pd.Series) -> xgb.XGBRegressor:
    model = xgb.XGBRegressor(
        objective='reg:pseudohubererror',
        max_depth=5,
        learning_rate=0.05,
        n_estimators=1000,
        early_stopping_rounds=100,
        n_jobs=-1
    )
    # Split some for internal early stopping 
    val_size = max(1, int(len(X_train)*0.2))
    Xt, yt = X_train.iloc[:-val_size], y_train.iloc[:-val_size]
    Xv, yv = X_train.iloc[-val_size:], y_train.iloc[-val_size:]
    
    model.fit(Xt, yt, eval_set=[(Xv, yv)], verbose=False)
    return model

def save_model(model: xgb.XGBRegressor, path: str):
    model.save_model(path)

def load_model(path: str) -> xgb.XGBRegressor:
    model = xgb.XGBRegressor()
    model.load_model(path)
    return model
