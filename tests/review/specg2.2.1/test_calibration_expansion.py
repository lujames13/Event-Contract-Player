# Review tests for task-spec-g2.2.1
# Focus: Edge cases in calibration analysis (Confidence Inversion, Empty Data, Consistent logic)

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scripts.analyze_calibration import run_calibration_analysis, estimate_avg_bet

def test_confidence_inversion_detection():
    # Synthetic data with intentional inversion
    # Bin [0.5, 0.6) -> high accuracy 80%
    # Bin [0.6, 0.7) -> low accuracy 40% (Inversion!)
    data = []
    for _ in range(50):
        data.append({"confidence": 0.55, "is_correct": 1 if np.random.random() < 0.8 else 0})
    for _ in range(50):
        data.append({"confidence": 0.65, "is_correct": 1 if np.random.random() < 0.4 else 0})
    
    df = pd.DataFrame(data)
    df['strategy_name'] = 'test_strat'
    df['timeframe_minutes'] = 60
    df['timestamp'] = datetime.now().isoformat()
    df['direction'] = 'higher'
    
    report = run_calibration_analysis(df, min_samples=10)
    
    # Check if inversion warning is in report
    assert "❌ 信心反轉" in report
    assert "重新訓練模型" in report

def test_ece_with_empty_bins():
    # Data only in one bin
    data = [{"confidence": 0.51, "is_correct": 1}] * 20
    df = pd.DataFrame(data)
    df['strategy_name'] = 'test_strat'
    df['timeframe_minutes'] = 60
    df['timestamp'] = datetime.now().isoformat()
    df['direction'] = 'higher'
    
    report = run_calibration_analysis(df, min_samples=10)
    
    # Should not crash and should show ECE
    assert "ECE" in report
    # abs(1.0 - 0.51) = 0.49
    assert "0.49" in report

def test_estimate_avg_bet_clamping():
    # Confidence at threshold
    conf = pd.Series([0.6])
    bet = estimate_avg_bet(conf, 0.6)
    assert bet == 5.0
    
    # Confidence at 1.0
    conf = pd.Series([1.0])
    bet = estimate_avg_bet(conf, 0.6)
    assert bet == 20.0
    
    # Confidence below threshold (should not happen if filtered, but let's check function behavior)
    # The function has "if conf >= threshold" check
    conf = pd.Series([0.5])
    bet = estimate_avg_bet(conf, 0.6)
    assert bet == 0.0

def test_drift_analysis_stable():
    # 60 samples, all accuracy ~60%
    data = []
    base_time = datetime.now() - timedelta(days=1)
    for i in range(60):
        data.append({
            "confidence": 0.6,
            "is_correct": 1 if i % 10 < 6 else 0,
            "strategy_name": "strat1",
            "timeframe_minutes": 60,
            "timestamp": (base_time + timedelta(minutes=i*10)).isoformat(),
            "direction": "higher"
        })
    df = pd.DataFrame(data)
    report = run_calibration_analysis(df, min_samples=5)
    assert "📊 穩定" in report

def test_drift_analysis_declining():
    # 60 samples, accuracy drops from 90% to 30%
    data = []
    base_time = datetime.now() - timedelta(days=1)
    for i in range(60):
        # Accuracy decreases over index i
        acc = 0.9 - (i / 60) * 0.6
        data.append({
            "confidence": 0.6,
            "is_correct": 1 if np.random.random() < acc else 0,
            "strategy_name": "strat1",
            "timeframe_minutes": 60,
            "timestamp": (base_time + timedelta(minutes=i*10)).isoformat(),
            "direction": "higher"
        })
    df = pd.DataFrame(data)
    report = run_calibration_analysis(df, min_samples=5)
    assert "⚠️ 下降趨勢" in report or "斜率 < -2" in report # The string check should be precise

def test_consecutive_consistency():
    # Force 3 consecutive higher results to be 100% correct
    data = []
    for i in range(20):
        data.append({
            "confidence": 0.6,
            "is_correct": 1 if i in [2, 3, 4] else 0, # Sequence at index 2,3,4
            "strategy_name": "strat1",
            "timeframe_minutes": 60,
            "timestamp": (datetime.now() + timedelta(minutes=i)).isoformat(),
            "direction": "higher" 
        })
    df = pd.DataFrame(data)
    report = run_calibration_analysis(df, min_samples=2)
    assert "=== 連續信號一致性" in report
    assert "3 連續" in report
    # The accuracy should be a number followed by %
    import re
    assert re.search(r"3 連續\s+\|\s+same\s+\|\s+\d+\s+\|\s+\d+\.\d+%", report)

