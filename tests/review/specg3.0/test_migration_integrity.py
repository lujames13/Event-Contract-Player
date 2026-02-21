# Review tests for task-spec-g3.0
# Focus: Structural integrity after migration and dataclass compliance

import os
import sys
import pytest
from pathlib import Path

def test_directory_structure():
    """Verify that all required directories were created."""
    project_root = Path(__file__).parent.parent.parent.parent
    expected_dirs = [
        "src/btc_predictor/binance",
        "src/btc_predictor/polymarket",
        "src/btc_predictor/strategies/pm_v1",
        "scripts/binance",
        "scripts/polymarket",
        "reports/binance",
        "tests/test_binance",
        "tests/test_polymarket",
        "docs/binance",
    ]
    for d in expected_dirs:
        assert (project_root / d).is_dir(), f"Directory {d} is missing"

def test_settler_migration():
    """Verify that settler.py was moved and functions are importable."""
    # Ensure src is in sys.path
    project_root = Path(__file__).parent.parent.parent.parent
    sys.path.insert(0, str(project_root / "src"))
    
    try:
        from btc_predictor.binance.settler import settle_pending_trades, settle_pending_signals
    except ImportError as e:
        pytest.fail(f"Failed to import from binance.settler: {e}")

def test_models_dataclass_compliance():
    """Verify if models.py was updated with Polymarket specific fields as required by ARCHITECTURE.md."""
    from btc_predictor.models import PredictionSignal
    import dataclasses
    
    fields = {f.name: f.type for f in dataclasses.fields(PredictionSignal)}
    
    # Required Polymarket fields according to ARCHITECTURE.md
    expected_pm_fields = [
        "market_slug",
        "market_price_up",
        "alpha",
        "order_type"
    ]
    
    missing_fields = [f for f in expected_pm_fields if f not in fields]
    assert not missing_fields, f"PredictionSignal is missing Polymarket fields: {missing_fields}"

def test_polymarket_order_exists():
    """Verify if PolymarketOrder dataclass exists in models.py."""
    try:
        from btc_predictor.models import PolymarketOrder
    except (ImportError, AttributeError):
        pytest.fail("PolymarketOrder is missing from btc_predictor.models")

def test_script_import_fix():
    """Check if scripts/binance/fetch_history.py can still run or at least has corrected paths."""
    project_root = Path(__file__).parent.parent.parent.parent
    script_path = project_root / "scripts/binance/fetch_history.py"
    
    # Check if the script contains the expected path adjustment
    content = script_path.read_text()
    assert ".parent.parent.parent" in content or "PROJECT_DIR" in content or "../../src" in content, "fetch_history.py might have broken pathing"
