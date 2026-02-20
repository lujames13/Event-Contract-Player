# Review tests for task-spec-g2.5.1
# Focus: vps_verify.py JSON structure and error handling

import subprocess
import json
import os
import pytest
from unittest.mock import patch, MagicMock

# We can't easily mock 'requests' inside vps_verify.py if we run it as a subprocess
# So we either run it as a module or expect it to fail gracefully on a dev machine.

def test_vps_verify_local_execution():
    """Run vps_verify.py locally and check JSON structure."""
    cmd = ["python3", "scripts/polymarket/vps_verify.py"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # It should still output JSON even if tests fail due to being in Taiwan
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"vps_verify.py did not output valid JSON. Output: {result.stdout}\nError: {result.stderr}")
        
    assert "meta" in data
    assert "tests" in data
    assert "conclusion" in data
    
    # Typical keys in meta
    meta = data["meta"]
    assert "timestamp" in meta
    assert "python_version" in meta
    
    # Check that all 6 (without --with-l1-auth) or 7 tests are present
    tests = data["tests"]
    expected_tests = ["geoblock", "clob_latency", "gamma_api", "clob_markets", "clob_orderbook", "websocket", "l1_auth"]
    for t in expected_tests:
        assert t in tests, f"Test {t} missing from output"

def test_vps_verify_l1_auth_flag():
    """Run vps_verify.py with --with-l1-auth flag."""
    cmd = ["python3", "scripts/polymarket/vps_verify.py", "--with-l1-auth"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    data = json.loads(result.stdout)
    assert data["tests"]["l1_auth"]["status"] != "SKIPPED" or "eth-account not installed" in data["tests"]["l1_auth"].get("error", "")
    # Note: if eth-account is not installed, it will be SKIPPED for that reason, which is also valid.
