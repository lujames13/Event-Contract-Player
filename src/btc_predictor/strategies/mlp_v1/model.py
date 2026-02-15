import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Tuple

class MLP(nn.Module):
    def __init__(self, input_dim: int):
        super(MLP, self).__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, 64),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(64, 1),
            nn.Sigmoid()
        )
        
    def forward(self, x):
        return self.net(x)

def train_mlp(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    val_data: Optional[Tuple[pd.DataFrame, pd.Series]] = None,
    epochs: int = 50,
    batch_size: int = 512,
    lr: float = 1e-3,
    weight_decay: float = 1e-5,
    patience: int = 10,
    device: str = 'cpu'
) -> MLP:
    input_dim = X_train.shape[1]
    model = MLP(input_dim).to(device)
    optimizer = optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
    criterion = nn.BCELoss()
    
    # Convert to tensors
    X_train_t = torch.tensor(X_train.values, dtype=torch.float32).to(device)
    y_train_t = torch.tensor(y_train.values, dtype=torch.float32).view(-1, 1).to(device)
    
    train_dataset = TensorDataset(X_train_t, y_train_t)
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    
    if val_data:
        X_val, y_val = val_data
        X_val_t = torch.tensor(X_val.values, dtype=torch.float32).to(device)
        y_val_t = torch.tensor(y_val.values, dtype=torch.float32).view(-1, 1).to(device)
        
    best_val_loss = float('inf')
    best_state = None
    early_stop_counter = 0
    
    for epoch in range(epochs):
        model.train()
        epoch_loss = 0
        for batch_X, batch_y in train_loader:
            optimizer.zero_grad()
            outputs = model(batch_X)
            loss = criterion(outputs, batch_y)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
            
        if val_data:
            model.eval()
            with torch.no_grad():
                val_outputs = model(X_val_t)
                val_loss = criterion(val_outputs, y_val_t).item()
                
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_state = model.state_dict()
                early_stop_counter = 0
            else:
                early_stop_counter += 1
                
            if early_stop_counter >= patience:
                print(f"Early stopping at epoch {epoch}")
                break
                
    if best_state is not None:
        model.load_state_dict(best_state)
        
    return model

def save_model(model: MLP, path: str):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), p)

def load_model(path: str, input_dim: int, device: str = 'cpu') -> MLP:
    model = MLP(input_dim).to(device)
    model.load_state_dict(torch.load(path, map_location=device))
    model.eval()
    return model
