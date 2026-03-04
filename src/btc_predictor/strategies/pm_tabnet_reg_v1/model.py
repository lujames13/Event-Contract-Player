from pytorch_tabnet.tab_model import TabNetRegressor
from typing import Tuple
import pandas as pd
import numpy as np
import torch
import os

def train_model(X_train: pd.DataFrame, y_train: pd.Series, val_data: Tuple[pd.DataFrame, pd.Series]) -> TabNetRegressor:
    model = TabNetRegressor(
        n_d=16, n_a=16,
        optimizer_fn=torch.optim.Adam,
        optimizer_params=dict(lr=2e-2),
        scheduler_params={"step_size":10, "gamma":0.9},
        scheduler_fn=torch.optim.lr_scheduler.StepLR,
        mask_type='entmax',
        device_name='cpu',
        verbose=0
    )
    
    X_val, y_val = val_data
    
    model.fit(
        X_train=X_train.values, y_train=y_train.values.reshape(-1, 1),
        eval_set=[(X_val.values, y_val.values.reshape(-1, 1))],
        eval_name=['val'],
        eval_metric=['mae'],
        max_epochs=30,
        patience=10,
        batch_size=256,
        virtual_batch_size=128
    )
    return model

def save_model(model: TabNetRegressor, path: str):
    base_path = path.replace(".zip", "")
    model.save_model(base_path)

def load_model(path: str) -> TabNetRegressor:
    model = TabNetRegressor()
    model.load_model(path)
    return model
