from catboost import CatBoostRegressor
from typing import Tuple
import pandas as pd

def train_model(X_train: pd.DataFrame, y_train: pd.Series) -> CatBoostRegressor:
    model = CatBoostRegressor(
        loss_function='Huber:delta=1.0',
        iterations=1000,
        learning_rate=0.05,
        depth=5,
        verbose=False
    )
    val_size = max(1, int(len(X_train)*0.2))
    Xt, yt = X_train.iloc[:-val_size], y_train.iloc[:-val_size]
    Xv, yv = X_train.iloc[-val_size:], y_train.iloc[-val_size:]
    
    model.fit(Xt, yt, eval_set=(Xv, yv), early_stopping_rounds=100, verbose=False)
    return model

def save_model(model: CatBoostRegressor, path: str):
    model.save_model(path)

def load_model(path: str) -> CatBoostRegressor:
    model = CatBoostRegressor()
    model.load_model(path)
    return model
