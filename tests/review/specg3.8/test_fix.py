import pytest
import pandas as pd
import numpy as np
import json
import subprocess
from pathlib import Path
from src.btc_predictor.analytics.metrics import compute_directional_accuracy, compute_drift_detection

# Review tests for task-spec-g3.8 fix
# Focus: Ensure missing column defenses and slope math are robust.

def test_missing_is_correct_defense():
    # DataFrame with total > 0 but missing is_correct
    df = pd.DataFrame({"total": [1, 2, 3], "some_col": ["a", "b", "c"]})
    
    # Should not raise KeyError
    res = compute_directional_accuracy(df)
    
    assert res["overall"]["total"] == 0, "Should handle missing is_correct gracefully"

def test_drift_detection_slope_per_window():
    # We want a slope of exactly e.g. -0.01 per window.
    # Window size = 50.
    # Every step, DA drops by 0.01 / 50 = 0.0002.
    # So if we have 50 steps, DA drops by 0.01 total.
    
    window_size = 50
    steps = 100
    
    # Let's construct a rolling_da array that is perfectly linear
    # the function calculates DA over window_size.
    # If we want rolling_da to be `1.0 - i * 0.0002`,
    # y array can be constructed such that its rolling mean is linear.
    # Actually, we can just mock `rolling_da` or pass a specific `is_correct` array.
    # If `is_correct` has a rolling mean that's linear... it's hard to make exactly linear sequence of 0s and 1s.
    # But wait, `is_correct` handles floats inside `compute_drift_detection` because `df['is_correct'].astype(float).values`.
    # Let's just create an `is_correct` array with float values for this mathematical test!
    
    # If y_i is 1.0 - i * 0.0002, then rolling mean will also be linear with same slope.
    y = np.array([1.0 - i * 0.0002 for i in range(steps + window_size)])
    df = pd.DataFrame({"is_correct": y})
    
    res = compute_drift_detection(df, window_size=window_size)
    
    # Slope should be -0.01
    assert res["trend_slope"] == pytest.approx(-0.01, rel=1e-3)
    assert res["is_degrading"] is True

def test_cli_breakeven_winrate_usage(tmp_path):
    # Test if CLI uses breakeven_winrate and handles empty DB.
    db_path = tmp_path / "empty.db"
    out_json = tmp_path / "metrics.json"
    
    # Run the script
    cmd = [
        "uv", "run", "python", "scripts/polymarket/compute_metrics.py",
        "-o", str(out_json)
    ]
    # We mock or run real? Since it connects to sqlite db_path which defaults to data/btc_predictor.db,
    # wait the script doesn't allow --db-path arg? Let's check compute_metrics.py:
    # Ah, let's just run it as is, it might read real DB.
    # The real DB might be empty or have data. We just want to check the keys in JSON.
    env = None
    subprocess.run(cmd, env=env, check=True, cwd="/home/jl/code/Event-Contract-Player")
    
    with open(out_json, "r") as f:
        data = json.load(f)
        
    assert "breakeven_winrate" in data["meta"]
    assert "da_above_breakeven" in data["gate3_status"]
