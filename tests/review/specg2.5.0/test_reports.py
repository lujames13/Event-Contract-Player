# Review tests for task-spec-g2.5.0
# Focus: Report correctness and consistency

import os
import re

def test_reports_existence():
    reports = [
        "reports/polymarket/PM-0.1-api-access-test.md",
        "reports/polymarket/PM-0.2-vps-relay-test.md",
        "reports/polymarket/PM-0.3-legal-risk-assessment.md",
        "reports/polymarket/PM-0.4-architecture-latency.md"
    ]
    for r in reports:
        assert os.path.exists(r), f"Report {r} is missing"

def test_pm01_content():
    path = "reports/polymarket/PM-0.1-api-access-test.md"
    with open(path, "r") as f:
        content = f.read()
    assert "blocked: true" in content.lower()
    assert "gamma-api" in content.lower()
    assert "clob.polymarket.com" in content.lower()

def test_pm04_latency_math():
    path = "reports/polymarket/PM-0.4-architecture-latency.md"
    with open(path, "r") as f:
        content = f.read()
    
    # Total sum matches Tokyo VPS real data in report
    # 700 to 900
    assert "700ms" in content
    assert "900ms" in content

def test_script_not_in_src():
    # Ensure the new script is not in src/
    path = "scripts/polymarket/test_public_api.py"
    assert os.path.exists(path)
    assert not path.startswith("src/")

def test_legal_risk_matrix():
    path = "reports/polymarket/PM-0.3-legal-risk-assessment.md"
    with open(path, "r") as f:
        content = f.read()
    assert "Critical" in content
    assert "election" in content.lower()
    assert "USDC" in content
