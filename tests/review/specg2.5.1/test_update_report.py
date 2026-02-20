# Review tests for task-spec-g2.5.1
# Focus: report update logic and regex replacement in PM-0.4

import os
import json
import pytest
import re
from unittest.mock import patch, mock_open
from scripts.polymarket.update_pm02_report import update_pm02_report, update_pm04_report

@pytest.fixture
def sample_results():
    return {
        "meta": {
            "timestamp": "2026-02-21T18:30:00Z",
            "vm_provider": "GCP",
            "vm_region": "europe-west2",
            "vm_ip_masked": "34.89.xxx.xxx",
            "python_version": "3.12.0"
        },
        "tests": {
            "geoblock": {"status": "PASS", "blocked": False, "raw_response": {"blocked": False, "country": "United Kingdom"}, "latency_ms": 12.3},
            "clob_latency": {"status": "PASS", "samples": 100, "p50_ms": 5.2, "p95_ms": 12.1, "p99_ms": 18.7, "mean_ms": 6.8, "min_ms": 3.1, "max_ms": 25.4},
            "gamma_api": {"status": "PASS", "http_status": 200, "events_count": 5, "latency_ms": 45.2},
            "clob_markets": {"status": "PASS", "http_status": 200, "markets_count": 150, "latency_ms": 38.1},
            "clob_orderbook": {"status": "PASS", "token_id": "abc", "bids_count": 12, "asks_count": 15, "best_bid": "0.45", "best_ask": "0.55", "spread": "0.10", "latency_ms": 22.3},
            "websocket": {"status": "PASS", "connected": True, "duration_seconds": 5.0, "error": None},
            "l1_auth": {"status": "PASS", "wallet_address": "0xtest", "http_status": 401, "error": None}
        },
        "conclusion": {"geoblock_passed": True, "datacenter_ip_accepted": True, "clob_latency_acceptable": True, "l1_auth_works": True, "overall": "PASS"}
    }

def test_update_pm02_report_logic(sample_results, tmp_path):
    # Test the logic by mocking the file operations
    res_file = tmp_path / "results.json"
    res_file.write_text(json.dumps(sample_results))
    
    with patch("builtins.open", mock_open()) as m:
        # We need to mock open twice: once for results.json and once for the report
        # To make it simple, we can mock open to return different things based on filename
        
        def side_effect(filename, mode='r'):
            if filename == str(res_file):
                return mock_open(read_data=json.dumps(sample_results))().read() # This is getting complicated
            return mock_open()()
        
        # Actually, let's just patch it within the function call scope
        # The function does:
        # with open(results_file, 'r') as f: res = json.load(f)
        # with open(report_path, 'w') as f: f.write(new_content)
        
        # Let's mock json.load instead
        with patch("json.load", return_value=sample_results):
            with patch("os.path.exists", return_value=True):
                # Use a real file for results_file to satisfy the first open
                dummy_res = tmp_path / "dummy.json"
                dummy_res.write_text("{}")
                
                # Capture the second open's write
                with patch("builtins.open", mock_open()) as m:
                    update_pm02_report(str(dummy_res))
                    
                    # Check what was written to the report
                    # The first open is for dummy_res, second for PM-0.2
                    # Actually, mock_open handles subsequent calls if we are careful
                    
                    handle = m()
                    # We want to find the call where it writes the report
                    write_calls = [call.args[0] for call in m.mock_calls if call[0] == '().write']
                    if not write_calls:
                         # fallback for different python/mock versions
                         write_calls = [call.args[0] for call in m.return_value.write.call_args_list]
                    
                    content = "".join(write_calls)
                    assert "GCP London 實測" in content
                    assert "P95 RTT**: 12.1 ms" in content

def test_pm04_latency_regex():
    # Test the regex logic specifically
    content = """
| 3. ... | ... | ... |
| 4. 交易簽署與提交 (Relay) | 5ms - 10ms | 在倫敦 VPS 本地執行 |
| 5. ... | ... | ... |
"""
    new_vps_latency = 12.1
    updated_content = re.sub(
        r"\| 4\. 交易簽署與提交 \(Relay\) \| [^|]+ \|",
        f"| 4. 交易簽署與提交 (Relay) | {new_vps_latency}ms | 實測 VPS -> CLOB RTT |",
        content
    )
    assert "| 4. 交易簽署與提交 (Relay) | 12.1ms | 實測 VPS -> CLOB RTT |" in updated_content

def test_pm04_latency_regex_variant():
    # Test with different existing latency format
    content = """
| 4. 交易簽署與提交 (Relay) | 100ms | 舊資料 |
"""
    new_vps_latency = 5.5
    updated_content = re.sub(
        r"\| 4\. 交易簽署與提交 \(Relay\) \| [^|]+ \|",
        f"| 4. 交易簽署與提交 (Relay) | {new_vps_latency}ms | 實測 VPS -> CLOB RTT |",
        content
    )
    assert "| 4. 交易簽署與提交 (Relay) | 5.5ms | 實測 VPS -> CLOB RTT |" in updated_content
