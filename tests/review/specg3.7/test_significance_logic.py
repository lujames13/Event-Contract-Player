# Review tests for task-spec-g3.7
# Focus: Statistical significance calculation and Gate 3 pass criteria

import pytest
import pandas as pd
import numpy as np
from scipy import stats
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path

# Add project root to sys.path to import the script
sys.path.append(str(Path(__file__).parent.parent.parent.parent))
from scripts.polymarket.verify_significance import run_validation

@pytest.fixture
def mock_db_data():
    def _create_mock_df(strategy, timeframe, n, win_rate, avg_pnl, pnl_std=0.01):
        wins_count = int(n * win_rate)
        
        # We want to construct pnl such that:
        # 1. wins_count entries are > 0
        # 2. n - wins_count entries are <= 0
        # 3. Mean is approx avg_pnl
        
        pnl_values = np.zeros(n)
        if n > 0:
            # Simple approach: set wins to some positive value, losses to some non-positive value
            # and adjust to match avg_pnl
            # Let's say wins are X, losses are Y.
            # wins_count * X + (n - wins_count) * Y = n * avg_pnl
            
            if wins_count == n:
                pnl_values[:] = avg_pnl
            elif wins_count == 0:
                pnl_values[:] = avg_pnl
            else:
                # Set wins to 1.0, and find Y
                # wins_count * 1.0 + (n - wins_count) * Y = n * avg_pnl
                # Y = (n * avg_pnl - wins_count) / (n - wins_count)
                # But we want to avoid extreme values. 
                # Let's just use two distinct values around avg_pnl
                # such that wins are > 0 and losses are <= 0.
                
                # If we want win_rate = 65% and avg_pnl = 0.05
                # We can have wins = 0.1, losses = -0.04
                # 0.65 * 0.1 + 0.35 * -0.04 = 0.065 - 0.014 = 0.051 (close enough)
                
                # Better: offset from avg_pnl
                pnl_values[:wins_count] = 0.1
                remaining_pnl = n * avg_pnl - wins_count * 0.1
                pnl_values[wins_count:] = remaining_pnl / (n - wins_count)
            
        return pd.DataFrame({
            'strategy_name': [strategy] * n,
            'timeframe_minutes': [timeframe] * n,
            'pnl': pnl_values,
            'is_correct': [1] * wins_count + [0] * (n - wins_count)
        })
    return _create_mock_df

@patch('scripts.polymarket.verify_significance.sqlite3.connect')
@patch('scripts.polymarket.verify_significance.pd.read_sql_query')
@patch('scripts.polymarket.verify_significance._write_markdown_report')
def test_gate3_pass_criteria(mock_write_report, mock_read_sql, mock_connect, mock_db_data):
    # Scenario: N=250, WinRate=65%, AvgPnL=0.05 (High Significance)
    # We need pnl_std to be smaller than avg_pnl or enough to keep win pnl > 0
    df_pass = mock_db_data("pm_pass", 240, 250, 0.65, 0.05, pnl_std=0.01)
    
    # Scenario: N=100, WinRate=70%, AvgPnL=0.10 (Insufficient N)
    df_low_n = mock_db_data("pm_low_n", 240, 100, 0.70, 0.10, pnl_std=0.01)
    
    # Scenario: N=250, WinRate=51%, AvgPnL=0.01 (Low DA Significance)
    df_low_da_sig = mock_db_data("pm_low_da", 240, 250, 0.51, 0.01, pnl_std=0.001)

    combined_df = pd.concat([df_pass, df_low_n, df_low_da_sig], ignore_index=True)
    mock_read_sql.return_value = combined_df
    
    # We need to capture the results passed to _write_markdown_report
    run_validation()
    
    args, _ = mock_write_report.call_args
    results = args[0]
    
    res_map = {r['strategy']: r for r in results}
    
    # 1. High significance should pass
    assert res_map['pm_pass']['passed'] == True
    assert res_map['pm_pass']['n'] == 250
    assert res_map['pm_pass']['da_pvalue'] < 0.05
    assert res_map['pm_pass']['pnl_pvalue'] < 0.05
    
    # 2. Low N should not pass
    assert res_map['pm_low_n']['passed'] == False
    assert res_map['pm_low_n']['n'] == 100
    
    # 3. Low DA significance should not pass (H0: DA <= 0.5)
    assert res_map['pm_low_da']['passed'] == False
    assert res_map['pm_low_da']['da_pvalue'] > 0.05

@patch('scripts.polymarket.verify_significance.sqlite3.connect')
@patch('scripts.polymarket.verify_significance.pd.read_sql_query')
@patch('scripts.polymarket.verify_significance._write_markdown_report')
def test_pnl_significance(mock_write_report, mock_read_sql, mock_connect, mock_db_data):
    # Scenario: N=250, WinRate=60%, AvgPnL=-0.01 (Negative PnL)
    # Ensure wins still have negative or zero PnL if avg is negative enough, 
    # but the script counts wins as pnl > 0.
    # Let's just test that negative avg PnL leads to high p-value.
    df_neg_pnl = mock_db_data("pm_neg_pnl", 240, 250, 0.60, -0.01, pnl_std=0.001)
    
    mock_read_sql.return_value = df_neg_pnl
    
    run_validation()
    
    args, _ = mock_write_report.call_args
    results = args[0]
    res = results[0]
    
    assert res['passed'] == False
    assert res['avg_pnl'] < 0
    assert res['pnl_pvalue'] > 0.5 # One-tailed t-test for 'greater'

@patch('scripts.polymarket.verify_significance.sqlite3.connect')
@patch('scripts.polymarket.verify_significance.pd.read_sql_query')
@patch('scripts.polymarket.verify_significance._write_markdown_report')
def test_empty_db_graceful_handle(mock_write_report, mock_read_sql, mock_connect):
    mock_read_sql.return_value = pd.DataFrame()
    
    # Should not crash
    run_validation()
    
    mock_write_report.assert_called_once()
    args, _ = mock_write_report.call_args
    assert args[0] == []
    assert "No settled Polymarket orders" in args[1]
