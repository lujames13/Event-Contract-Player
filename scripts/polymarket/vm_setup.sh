#!/usr/bin/env bash
# 在 GCP europe-west2 VM 上執行
# Usage: bash vm_setup.sh

set -euo pipefail

echo "=== PM-0.2 VPS Verification Setup ==="

# 1. 確認 Python 3 可用
python3 --version || { echo "❌ Python3 not found"; exit 1; }

# 2. 安裝最小依賴
echo "Installing dependencies (requests, eth-account)..."

# Try to check if pip is available via python module
if ! python3 -m pip --version >/dev/null 2>&1; then
    echo "⚠️ pip not found. Attempting to install python3-pip via apt..."
    sudo apt-get update && sudo apt-get install -y python3-pip || {
        echo "❌ Failed to install python3-pip. Please install it manually."
    }
fi

# Try installation using python3 -m pip (preferred)
python3 -m pip install --user requests eth-account || {
    echo "⚠️ Standard pip install failed, trying with --break-system-packages if on newer Debian/Ubuntu"
    python3 -m pip install --user requests eth-account --break-system-packages || echo "❌ Failed to install dependencies"
}

# 3. 記錄 VM 資訊
echo "VM IP: $(curl -s ifconfig.me)"
echo "Region: $(curl -s -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/instance/zone 2>/dev/null || echo 'unknown')"

# 4. 快速 smoke test
python3 -c "import requests; print('✅ requests OK')" 2>/dev/null || echo "❌ requests conversion failed"
python3 -c "from eth_account import Account; print('✅ eth-account OK')" 2>/dev/null || \
  echo "⚠️ eth-account not available, L1 auth test will be skipped"

echo "=== Setup Complete. ==="
echo "Run: python3 vps_verify.py --with-l1-auth"
