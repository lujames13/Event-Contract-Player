import lightgbm as lgb
from typing import Tuple
import pandas as pd

def train_model(X_train: pd.DataFrame, y_train: pd.Series) -> lgb.LGBMRegressor:
    model = lgb.LGBMRegressor(
        objective='huber',
        max_depth=5,
        learning_rate=0.05,
        n_estimators=1000,
        n_jobs=-1,
        verbose=-1
    )
    val_size = max(1, int(len(X_train)*0.2))
    Xt, yt = X_train.iloc[:-val_size], y_train.iloc[:-val_size]
    Xv, yv = X_train.iloc[-val_size:], y_train.iloc[-val_size:]
    
    model.fit(
        Xt, yt, 
        eval_set=[(Xv, yv)],
        callbacks=[lgb.early_stopping(100, verbose=False)]
    )
    return model

def save_model(model: lgb.LGBMRegressor, path: str):
    model.booster_.save_model(path)

def load_model(path: str) -> lgb.LGBMRegressor:
    booster = lgb.Booster(model_file=path)
    return booster
