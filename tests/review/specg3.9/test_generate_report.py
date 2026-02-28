import pytest
import sqlite3
import json
import subprocess
import sys
from pathlib import Path

# Review tests for task-spec-g3.9
# Focus: Ensure metrics_report generation handles valid, partial, and invalid edge cases elegantly without unhandled exceptions.

def run_script(input_path, output_path):
    cmd = [
        sys.executable, "scripts/polymarket/generate_report.py",
        "--input", str(input_path),
        "--output", str(output_path)
    ]
    env = {"PYTHONPATH": "src", **__import__("os").environ}
    return subprocess.run(cmd, env=env, cwd="/home/jl/code/Event-Contract-Player", capture_output=True, text=True)

def test_generate_report_missing_file(tmp_path):
    """If metrics.json doesn't exist, it should exit cleanly with a clear message, without stacktrace."""
    res = run_script(tmp_path / "non_existent.json", tmp_path / "out.md")
    
    assert res.returncode != 0
    assert "Traceback" not in res.stderr, "Encountered unhandled exception stacktrace!"
    assert "does not exist" in res.stderr or "Error" in res.stderr

def test_generate_report_invalid_json(tmp_path):
    """If metrics.json is corrupted, it should exit cleanly with a clear message."""
    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("This is not a JSON object")
    
    res = run_script(invalid_json, tmp_path / "out.md")
    
    assert res.returncode != 0
    assert "Traceback" not in res.stderr, "Encountered unhandled exception stacktrace!"
    assert "Invalid JSON" in res.stderr or "Error" in res.stderr

def test_generate_report_missing_keys_graceful(tmp_path):
    """Test generating a report with an empty dict, should not raise KeyError."""
    empty_json = tmp_path / "empty.json"
    empty_json.write_text("{}")
    
    out_md = tmp_path / "empty_out.md"
    res = run_script(empty_json, out_md)
    
    # Should succeed because .get() fallback should be used everywhere
    assert res.returncode == 0, f"Script failed on empty JSON: {res.stderr}"
    assert "Traceback" not in res.stderr
    assert out_md.exists()
    
    content = out_md.read_text()
    # Basic sections should be present even if data is 'N/A' or 0
    assert "Overview / Meta" in content
    assert "Gate 3 Status" in content
    assert "Core Metrics" in content

def test_generate_report_drift_warning(tmp_path):
    """Test if drift degradation produces a warning string."""
    warnings_json = tmp_path / "warning.json"
    warnings_json.write_text(json.dumps({
        "drift": {
            "is_degrading": True
        }
    }))
    
    out_md = tmp_path / "warning_out.md"
    res = run_script(warnings_json, out_md)
    assert res.returncode == 0
    content = out_md.read_text()
    assert "WARNING" in content and "DRIFT" in content
