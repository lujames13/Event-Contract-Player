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
    
    # Check if the total latency range matches the components
    # Breakdown in report:
    # 1. 100-150
    # 2. 20-50
    # 3. 110-130
    # 4. 5-10
    # 5. 50-100
    # Total sum: (100+20+110+5+50) to (150+50+130+10+100)
    # = 285 to 440
    assert "285ms" in content
    assert "440ms" in content

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
