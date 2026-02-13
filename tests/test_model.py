import pytest
import pandas as pd
import numpy as np
import os
from btc_predictor.strategies.xgboost_direction.model import train_model, predict_higher_probability, save_model, load_model

@pytest.fixture
def mock_training_data():
    np.random.seed(42)
    n_samples = 100
    n_features = 10
    X = pd.DataFrame(np.random.randn(n_samples, n_features), columns=[f'feat_{i}' for i in range(n_features)])
    # y is 1 if feat_0 + feat_1 > 0 else 0
    y = (X['feat_0'] + X['feat_1'] > 0).astype(int)
    return X, y

def test_train_predict(mock_training_data):
    X, y = mock_training_data
    model = train_model(X, y)
    
    probs = predict_higher_probability(model, X)
    assert len(probs) == len(X)
    assert np.all(probs >= 0) and np.all(probs <= 1)
    
    # Simple check for "learning"
    preds = (probs > 0.5).astype(int)
    accuracy = (preds == y).mean()
    assert accuracy > 0.7 # Should be high since data is linearly separable

def test_save_load(mock_training_data, tmp_path):
    X, y = mock_training_data
    model = train_model(X, y)
    
    model_path = os.path.join(tmp_path, "model.pkl")
    save_model(model, model_path)
    assert os.path.exists(model_path)
    
    loaded_model = load_model(model_path)
    
    orig_probs = predict_higher_probability(model, X)
    loaded_probs = predict_higher_probability(loaded_model, X)
    
    np.testing.assert_array_almost_equal(orig_probs, loaded_probs)

def test_train_with_val_data(mock_training_data):
    X, y = mock_training_data
    X_train, X_val = X[:80], X[80:]
    y_train, y_val = y[:80], y[80:]
    
    model = train_model(X_train, y_train, val_data=(X_val, y_val))
    assert model is not None
