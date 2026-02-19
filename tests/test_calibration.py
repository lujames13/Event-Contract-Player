import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from btc_predictor.data.store import DataStore
import os
import subprocess

@pytest.fixture
def store():
    db_path = "data/test_calibration.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    store = DataStore(db_path)
    yield store
    if os.path.exists(db_path):
        os.remove(db_path)

def test_get_settled_signals_all(store):
    # Setup: Save some signals
    class MockSignal:
        def __init__(self, strategy, tf, confidence):
            self.strategy_name = strategy
            self.timeframe_minutes = tf
            self.timestamp = datetime.now()
            self.direction = "higher"
            self.confidence = confidence
            self.current_price = 50000.0
            self.features_used = {}

    s1 = MockSignal("strat1", 60, 0.6)
    s2 = MockSignal("strat2", 60, 0.7)
    
    id1 = store.save_prediction_signal(s1)
    id2 = store.save_prediction_signal(s2)
    
    # Settle them
    store.settle_signal(id1, "higher", 51000.0, True)
    store.settle_signal(id2, "lower", 49000.0, False)
    
    # Add an unsettled one
    s3 = MockSignal("strat1", 60, 0.8)
    store.save_prediction_signal(s3)
    
    df = store.get_settled_signals()
    assert len(df) == 2
    assert id1 in df['id'].values
    assert id2 in df['id'].values

def test_get_settled_signals_filtering(store):
    class MockSignal:
        def __init__(self, strategy, tf):
            self.strategy_name = strategy
            self.timeframe_minutes = tf
            self.timestamp = datetime.now()
            self.direction = "higher"
            self.confidence = 0.6
            self.current_price = 50000.0
            self.features_used = {}

    id1 = store.save_prediction_signal(MockSignal("strat1", 60))
    id2 = store.save_prediction_signal(MockSignal("strat1", 30))
    id3 = store.save_prediction_signal(MockSignal("strat2", 60))
    
    store.settle_signal(id1, "higher", 51000.0, True)
    store.settle_signal(id2, "higher", 51000.0, True)
    store.settle_signal(id3, "higher", 51000.0, True)
    
    # Filter by strategy
    df = store.get_settled_signals(strategy_name="strat1")
    assert len(df) == 2
    
    # Filter by timeframe
    df = store.get_settled_signals(timeframe_minutes=30)
    assert len(df) == 1
    assert df.iloc[0]['id'] == id2

def test_calibration_script_runs():
    process = subprocess.run(["python", "scripts/analyze_calibration.py", "--help"], capture_output=True, text=True)
    assert process.returncode == 0
    assert "Calibration Analysis Tool" in process.stdout

def test_ece_calculation():
    # Synthetic data: perfect calibration
    # Bin [0.5, 0.6) -> mean conf 0.55, accuracy 0.55
    data = []
    # Bin 0.5-0.6 (Mean 0.55)
    for _ in range(55): data.append({"confidence": 0.55, "is_correct": 1})
    for _ in range(45): data.append({"confidence": 0.55, "is_correct": 0})
    # Bin 0.6-0.65 (Mean 0.62)
    for _ in range(62): data.append({"confidence": 0.62, "is_correct": 1})
    for _ in range(38): data.append({"confidence": 0.62, "is_correct": 0})
    
    df = pd.DataFrame(data)
    df['strategy_name'] = 'test'
    df['timeframe_minutes'] = 60
    df['timestamp'] = datetime.now().isoformat()
    df['direction'] = 'higher'
    
    from scripts.analyze_calibration import run_calibration_analysis
    report = run_calibration_analysis(df, min_samples=10)
    
    # ECE should be near 0
    assert "ECE (Expected Calibration Error): 0.0000" in report

def test_optimal_threshold_search_logic():
    # Synthetic data: 
    # accuracy = 74% if conf > 0.55
    # accuracy = 50% if conf <= 0.55
    data = []
    # 0.50 - 0.55 (acc 50%)
    for i in range(50):
        data.append({"confidence": 0.52, "is_correct": 1 if i < 25 else 0})
    # 0.56 - 0.70 (acc 74%)
    for i in range(50):
        data.append({"confidence": 0.60, "is_correct": 1 if i < 37 else 0})
        
    df = pd.DataFrame(data)
    df['strategy_name'] = 'test'
    df['timeframe_minutes'] = 60
    df['timestamp'] = (datetime.now() - timedelta(days=1)).isoformat()
    # Ensure some duration
    df.loc[df.index[-1], 'timestamp'] = datetime.now().isoformat()
    df['direction'] = 'higher'

    from scripts.analyze_calibration import run_calibration_analysis
    report = run_calibration_analysis(df, min_samples=10)
    
    # Optimal threshold should be around 0.56 or higher (where accuracy jumps)
    assert "最佳閾值（最大化 E[PnL/day]）: 0.53" in report or "最佳閾值（最大化 E[PnL/day]）: 0.54" in report or "最佳閾值（最大化 E[PnL/day]）: 0.55" in report

def test_calibration_with_synthetic_data_full_flow():
    # Create 60 samples to trigger drift analysis
    data = []
    base_time = datetime.now() - timedelta(days=1)
    for i in range(60):
        data.append({
            "confidence": 0.5 + (i % 20) / 40.0,
            "is_correct": 1 if i % 2 == 0 else 0,
            "strategy_name": "strat1",
            "timeframe_minutes": 60,
            "timestamp": (base_time + timedelta(minutes=i*10)).isoformat(),
            "direction": "higher" if (i // 5) % 2 == 0 else "lower"
        })
    df = pd.DataFrame(data)
    
    from scripts.analyze_calibration import run_calibration_analysis
    report = run_calibration_analysis(df, min_samples=5)
    
    assert "=== 校準曲線 (Calibration Curve) ===" in report
    assert "=== 最佳閾值搜尋 (Optimal Threshold Search) ===" in report
    assert "=== 時間窗口演化 (Time Window Evolution) ===" in report
    assert "=== 連續信號一致性 (Consecutive Signal Consistency) ===" in report
    assert "=== 綜合建議 ===" in report
