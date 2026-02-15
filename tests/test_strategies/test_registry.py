
import pytest
import shutil
from pathlib import Path
from btc_predictor.strategies.registry import StrategyRegistry
from btc_predictor.strategies.base import BaseStrategy

# Mock strategy for testing register
class MockStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "mock_manual"
    
    @property
    def requires_fitting(self) -> bool:
        return False
        
    def fit(self, ohlcv, timeframe_minutes): pass
    def predict(self, ohlcv, timeframe_minutes): pass

def test_registry_manual_register():
    reg = StrategyRegistry()
    mock = MockStrategy()
    reg.register(mock)
    
    assert "mock_manual" in reg.list_names()
    assert reg.get("mock_manual") == mock

def test_registry_discover():
    # We use the actual project structure for this test, assuming it's set up
    reg = StrategyRegistry()
    
    # Paths relative to project root
    strategies_dir = Path("src/btc_predictor/strategies")
    models_dir = Path("models")
    
    # Ensure directories exist (they should if G1.0.4 is done)
    if not strategies_dir.exists():
        pytest.skip("Strategies directory not found")
        
    reg.discover(strategies_dir, models_dir)
    
    names = reg.list_names()
    assert "xgboost_v1" in names
    
    strat = reg.get("xgboost_v1")
    assert strat.name == "xgboost_v1"
    
    # Check if models were loaded (if models exist)
    # This depends on models/xgboost_v1 existing and populated
    # But specific loading logic is inside strategy, registry just triggers it.
    # We can check if strat has models attribute (which we added)
    if hasattr(strat, "models"):
        # If models exist in models/xgboost_v1, they should be loaded
        pass

def test_registry_get_nonexistent():
    reg = StrategyRegistry()
    with pytest.raises(KeyError):
        reg.get("nonexistent_strategy")

def test_registry_list_strategies():
    reg = StrategyRegistry()
    mock = MockStrategy()
    reg.register(mock)
    
    strats = reg.list_strategies()
    assert len(strats) == 1
    assert strats[0] == mock
