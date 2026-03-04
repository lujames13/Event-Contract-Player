import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader
import numpy as np

def train_pytorch(model, X_train, y_train, X_val, y_val, epochs=20, batch_size=256):
    X_t = torch.tensor(X_train, dtype=torch.float32)
    y_t = torch.tensor(y_train, dtype=torch.float32).unsqueeze(1)
    X_v = torch.tensor(X_val, dtype=torch.float32)
    y_v = torch.tensor(y_val, dtype=torch.float32).unsqueeze(1)
    
    train_dl = DataLoader(TensorDataset(X_t, y_t), batch_size=batch_size, shuffle=True)
    val_dl = DataLoader(TensorDataset(X_v, y_v), batch_size=batch_size)
    
    criterion = nn.HuberLoss(delta=1.0)
    optimizer = optim.Adam(model.parameters(), lr=1e-3)
    
    best_loss = float('inf')
    best_weights = model.state_dict()
    patience = 10
    strikes = 0
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model.to(device)
    
    for epoch in range(epochs):
        model.train()
        for bx, by in train_dl:
            bx, by = bx.to(device), by.to(device)
            optimizer.zero_grad()
            pred = model(bx)
            loss = criterion(pred, by)
            loss.backward()
            optimizer.step()
            
        model.eval()
        val_loss = 0
        with torch.no_grad():
            for bx, by in val_dl:
                bx, by = bx.to(device), by.to(device)
                val_loss += criterion(model(bx), by).item() * len(bx)
        val_loss /= len(X_v)
        
        if val_loss < best_loss:
            best_loss = val_loss
            strikes = 0
            best_weights = {k: v.cpu() for k, v in model.state_dict().items()}
        else:
            strikes += 1
            if strikes >= patience:
                break
                
    model.load_state_dict(best_weights)
    model.cpu()
    return model

class MLPRegressorWrapper:
    def __init__(self, model):
        self.model = model
        self.model.eval()
        
    def predict(self, X):
        import pandas as pd
        if isinstance(X, pd.DataFrame):
            X = X.values
        X_t = torch.tensor(X, dtype=torch.float32)
        with torch.no_grad():
            return self.model(X_t).numpy().flatten()

class MLP(nn.Module):
    def __init__(self, in_features):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_features, 128),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, 1)
        )
    def forward(self, x):
        return self.net(x)

def train_model(X_train, y_train, val_data) -> MLPRegressorWrapper:
    X_val, y_val = val_data
    # Extract values if DataFrame
    X_t = X_train.values if hasattr(X_train, 'values') else X_train
    y_t = y_train.values if hasattr(y_train, 'values') else y_train
    X_v = X_val.values if hasattr(X_val, 'values') else X_val
    y_v = y_val.values if hasattr(y_val, 'values') else y_val
    
    model = MLP(X_t.shape[1])
    model = train_pytorch(model, X_t, y_t, X_v, y_v)
    return MLPRegressorWrapper(model)

def save_model(model: MLPRegressorWrapper, path: str):
    torch.save(model.model.state_dict(), path)

def load_model(path: str) -> MLPRegressorWrapper:
    # 29 is the number of features of Feature Set A
    model = MLP(29)
    model.load_state_dict(torch.load(path, map_location='cpu'))
    return MLPRegressorWrapper(model)
