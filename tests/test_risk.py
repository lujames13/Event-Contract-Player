import pytest
from btc_predictor.simulation.risk import should_trade, calculate_bet
from unittest.mock import patch

@pytest.fixture
def mock_constants():
    return {
        "risk_control": {
            "bet_sizing": "dynamic",
            "bet_range": [5, 20],
            "confidence_to_bet": "linear",
            "daily_max_loss": 50,
            "max_consecutive_losses": 8,
            "max_daily_trades": 30
        },
        "confidence_thresholds": {
            10: 0.606,
            30: 0.591,
            60: 0.591,
            1440: 0.591
        }
    }

def test_should_trade_allowed(mock_constants):
    with patch("btc_predictor.simulation.risk.load_constants", return_value=mock_constants):
        assert should_trade(0, 0, 0) is True
        assert should_trade(49.9, 7, 29) is True

def test_should_trade_max_loss(mock_constants):
    with patch("btc_predictor.simulation.risk.load_constants", return_value=mock_constants):
        assert should_trade(50, 0, 0) is False
        assert should_trade(51, 0, 0) is False

def test_should_trade_max_trades(mock_constants):
    with patch("btc_predictor.simulation.risk.load_constants", return_value=mock_constants):
        assert should_trade(0, 0, 30) is False
        assert should_trade(0, 0, 31) is False

def test_should_trade_consecutive_losses(mock_constants):
    with patch("btc_predictor.simulation.risk.load_constants", return_value=mock_constants):
        assert should_trade(0, 8, 0) is False
        assert should_trade(0, 9, 0) is False

def test_calculate_bet_interpolation(mock_constants):
    with patch("btc_predictor.simulation.risk.load_constants", return_value=mock_constants):
        # 10m timeframe, threshold 0.606
        # Min confidence (threshold) -> Min bet (5)
        assert calculate_bet(0.606, 10) == 5.0
        
        # Max confidence (1.0) -> Max bet (20)
        # 1.0 - 0.606 = 0.394; (1.0 - 0.606)/0.394 = 1.0; 5 + 15 * 1.0 = 20.0
        assert calculate_bet(1.0, 10) == 20.0
        
        # Middle
        # (0.606 + 1.0) / 2 = 0.803
        # 5 + 15 * (0.803 - 0.606) / (1.0 - 0.606) = 5 + 15 * 0.197 / 0.394 = 5 + 15 * 0.5 = 12.5
        assert calculate_bet(0.803, 10) == 12.5

def test_calculate_bet_below_threshold(mock_constants):
    with patch("btc_predictor.simulation.risk.load_constants", return_value=mock_constants):
        assert calculate_bet(0.5, 10) == 0.0
        assert calculate_bet(0.605, 10) == 0.0

def test_calculate_bet_different_timeframes(mock_constants):
    with patch("btc_predictor.simulation.risk.load_constants", return_value=mock_constants):
        # 30m threshold is 0.591
        assert calculate_bet(0.591, 30) == 5.0
        
        # 1440m threshold is 0.591
        assert calculate_bet(0.591, 1440) == 5.0
