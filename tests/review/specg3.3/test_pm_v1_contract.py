# Review tests for task-spec-g3.3
# Focus: PredictionSignal contract, SimulatedTrade Literals, and Backtest Engine logic.

import pytest
import pandas as pd
import numpy as np
from datetime import datetime
from btc_predictor.models import PredictionSignal, SimulatedTrade
from btc_predictor.strategies.pm_v1.strategy import PMV1Strategy
from btc_predictor.backtest.engine import _process_fold

@pytest.fixture
def mock_ohlcv():
    dates = pd.date_range("2024-01-01", periods=10, freq="1h")
    df = pd.DataFrame({
        "open": [50000.0] * 10,
        "high": [50100.0] * 10,
        "low": [49900.0] * 10,
        "close": [50000.0] * 10,
        "volume": [1.0] * 10
    }, index=dates)
    return df

def test_pm_v1_prediction_signal_contract(mock_ohlcv):
    """驗證 pm_v1 輸出的 PredictionSignal 完全符合 ARCHITECTURE.md 契約"""
    strategy = PMV1Strategy()
    
    # Mock a model to return 0.6 prob
    class MockModel:
        def predict_proba(self, X):
            return np.array([[0.4, 0.6]])
    strategy.models[240] = MockModel()
    
    signal = strategy.predict(mock_ohlcv, 240)
    
    # 檢查通用欄位
    assert isinstance(signal.strategy_name, str)
    assert isinstance(signal.timestamp, datetime)
    assert signal.direction in ["higher", "lower"]
    assert isinstance(signal.confidence, float)
    assert isinstance(signal.timeframe_minutes, int)
    assert isinstance(signal.current_price, float)
    assert isinstance(signal.features_used, list)
    for feat in signal.features_used:
        assert isinstance(feat, str)
    
    # 檢查 Polymarket 擴展欄位
    assert signal.market_slug is not None
    assert isinstance(signal.market_price_up, float)
    assert isinstance(signal.alpha, float)
    assert signal.alpha == pytest.approx(0.6 - 0.5)

def test_simulated_trade_literals():
    """驗證 SimulatedTrade.timeframe_minutes 支援 5, 15, 240"""
    # 這裡主要是型別檢查，執行時若 Literal 不匹配，靜態檢查會報錯，
    # 但 Python 執行時不會強制噴錯除非有運算邏輯依賴它。
    # 我們檢查是否可以成功建立實例。
    for tf in [5, 15, 240]:
        trade = SimulatedTrade(
            id="test-id",
            strategy_name="pm_v1",
            direction="higher",
            confidence=0.6,
            timeframe_minutes=tf, # type: ignore
            bet_amount=10.0,
            open_time=datetime.now(),
            open_price=50000.0,
            expiry_time=datetime.now(),
            result="win",
            pnl=10.0
        )
        assert trade.timeframe_minutes == tf

def test_engine_settlement_condition_ge():
    """驗證 backtest engine 正確處理 >= 結算條件"""
    from btc_predictor.strategies.base import BaseStrategy
    
    class MockFixedStrategy(BaseStrategy):
        @property
        def name(self): return "mock"
        @property
        def requires_fitting(self): return False
        def predict(self, ohlcv, tf):
            return PredictionSignal(
                strategy_name="mock",
                timestamp=ohlcv.index[-1],
                direction="higher",
                confidence=0.6,
                timeframe_minutes=tf,
                current_price=ohlcv["close"].iloc[-1],
                features_used=[]
            )
        def fit(self, ohlcv, tf): pass

    # Case 1: Close == Open, condition ">=" -> Win for "higher"
    ohlcv = pd.DataFrame({
        "open": [50000.0, 50000.0],
        "high": [50000.0, 50000.0],
        "low": [50000.0, 50000.0],
        "close": [50000.0, 50000.0],
        "volume": [1.0, 1.0]
    }, index=pd.to_datetime(["2024-01-01 00:00:00", "2024-01-01 04:00:00"]))
    
    with patch("btc_predictor.backtest.engine.calculate_bet", return_value=10.0):
        trades = _process_fold(
            fold_start=pd.Timestamp("2024-01-01 00:00:00"),
            fold_end=pd.Timestamp("2024-01-02 00:00:00"),
            train_days=0,
            ohlcv=ohlcv,
            strategy=MockFixedStrategy(),
            timeframe_minutes=240,
            payout_ratio=2.0,
            settlement_condition=">="
        )
        
    assert len(trades) == 1
    assert trades[0].result == "win"

    # Case 2: Close == Open, condition ">" -> Lose for "higher"
    with patch("btc_predictor.backtest.engine.calculate_bet", return_value=10.0):
        trades_binance = _process_fold(
            fold_start=pd.Timestamp("2024-01-01 00:00:00"),
            fold_end=pd.Timestamp("2024-01-02 00:00:00"),
            train_days=0,
            ohlcv=ohlcv,
            strategy=MockFixedStrategy(),
            timeframe_minutes=240,
            payout_ratio=1.85,
            settlement_condition=">"
        )
    assert len(trades_binance) == 1
    assert trades_binance[0].result == "lose"

from unittest.mock import patch
