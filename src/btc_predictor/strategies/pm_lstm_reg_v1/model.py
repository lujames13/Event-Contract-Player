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
    
    device = torch.device('cpu')
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

class LSTMRegressorWrapper:
    def __init__(self, model):
        self.model = model
        self.model.eval()
        
    def predict(self, X):
        X_t = torch.tensor(X, dtype=torch.float32)
        with torch.no_grad():
            return self.model(X_t).numpy().flatten()

class LSTMNet(nn.Module):
    def __init__(self, features=5):
        super().__init__()
        self.lstm = nn.LSTM(input_size=features, hidden_size=64, num_layers=2, batch_first=True, dropout=0.2)
        self.fc = nn.Linear(64, 1)
        
    def forward(self, x):
        out, _ = self.lstm(x)
        out = out[:, -1, :] 
        return self.fc(out)

def train_model(X_train, y_train, val_data) -> LSTMRegressorWrapper:
    X_val, y_val = val_data
    model = LSTMNet(features=X_train.shape[2])
    model = train_pytorch(model, X_train, y_train, X_val, y_val)
    return LSTMRegressorWrapper(model)

def save_model(model: LSTMRegressorWrapper, path: str):
    torch.save(model.model.state_dict(), path)

def load_model(path: str) -> LSTMRegressorWrapper:
    model = LSTMNet(features=5)
    model.load_state_dict(torch.load(path, map_location='cpu'))
    return LSTMRegressorWrapper(model)
