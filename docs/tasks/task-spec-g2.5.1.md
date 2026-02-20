# Task Spec G2.5.1 — PM-0.2 實機驗證：GCP London VM 存取測試

<!-- status: done -->
<!-- created: 2026-02-21 -->
<!-- architect: Claude Opus (Chat Project) -->

> **Gate:** 2.5（Polymarket Feasibility Study）
> **優先級:** 🔴 High — PM-0 Go/No-Go 的最後一塊拼圖
> **前置條件:** G2.5.0 完成（PM-0.1~0.4 報告已產出）
> **執行者:** Coding agent 寫腳本 → **使用者本人**在 GCP VM 上執行 → git commit 回 repo

---

## 目標

PM-0.2 的 coding agent 版本因無法操作真實 VPS，結論基於模擬數據（ping Oxford 學術主機）。本 task 產出一套**可在 GCP europe-west2 (London) VM 上一鍵執行的腳本**，驗證以下 PM-0 遺留的關鍵假設：

1. **Geoblock 解除**：London datacenter IP 是否被 Polymarket 視為 `blocked: false`
2. **CLOB API 延遲**：VPS → Polymarket CLOB 的真實 RTT（p50/p95/p99）
3. **L1 認證可行性**：能否在 datacenter IP 上完成 `py-clob-client` 的 wallet signing → derive API key
4. **WebSocket 穩定性**：能否從 London VM 建立並維持 CLOB WebSocket 連線
5. **台灣 → London VM RTT**：使用者從台灣 SSH 到 VM 的實際延遲

結果將**覆寫** `reports/polymarket/PM-0.2-vps-relay-test.md`，從模擬數據升級為實測數據。

---

## 子任務

### G2.5.1.0 — 主測試腳本

**新增檔案：** `scripts/polymarket/vps_verify.py`

這是使用者在 GCP VM 上執行的唯一入口。腳本需要：

1. **零外部依賴啟動**：只用 Python 標準庫 + `requests`（pip install 一個套件）
   - 不依賴 `py-clob-client`（它的依賴樹太深，在乾淨 VM 上裝可能出問題）
   - L1 認證改用 `eth_account` + 手動 HTTP 呼叫模擬
2. **自動產出結構化 JSON 報告**：輸出到 `stdout`，使用者 redirect 到檔案即可
3. **每個測試獨立 try/catch**：一個測試失敗不影響其他測試

**測試項目與順序：**

```
Test 1: Geoblock Check
  → GET https://polymarket.com/api/geoblock
  → 記錄完整 JSON response

Test 2: CLOB API Latency (100 次取樣)
  → GET https://clob.polymarket.com/time
  → 計算 p50/p95/p99/mean/min/max

Test 3: Gamma API 存取
  → GET https://gamma-api.polymarket.com/events?active=true&closed=false&limit=5
  → 記錄 status code + response 前 500 chars

Test 4: CLOB Markets 存取
  → GET https://clob.polymarket.com/markets
  → 記錄 status code + 市場數量

Test 5: CLOB Order Book 深度
  → 從 Test 4 結果中取第一個 market 的 token_id
  → GET https://clob.polymarket.com/book?token_id={token_id}
  → 記錄 bids/asks 數量 + best bid/ask price

Test 6: WebSocket 連線測試
  → 用標準庫 (不依賴 websockets 套件) 或 subprocess 呼叫 curl
  → 嘗試連線 wss://ws-subscriptions-clob.polymarket.com/ws/market
  → 記錄：能否建立連線、維持多久

Test 7: L1 認證測試 (可選，需要 eth-account)
  → 產生臨時測試錢包（不入金）
  → 嘗試 derive API key
  → 記錄成功/失敗 + 錯誤訊息
  → 如果 eth-account 裝不上，標記 SKIPPED 並記錄原因
```

**CLI 介面：**

```bash
# 基本執行（Test 1-6，不需要額外套件）
python3 vps_verify.py

# 包含 L1 認證測試（需要先 pip install eth-account requests）
python3 vps_verify.py --with-l1-auth

# 輸出到檔案
python3 vps_verify.py --with-l1-auth 2>&1 | tee vps_verify_results.json
```

**輸出格式（JSON）：**

```json
{
  "meta": {
    "timestamp": "2026-02-21T18:30:00Z",
    "vm_provider": "GCP",
    "vm_region": "europe-west2 (London)",
    "vm_ip_masked": "34.89.xxx.xxx",
    "python_version": "3.12.x"
  },
  "tests": {
    "geoblock": {
      "status": "PASS|FAIL",
      "blocked": false,
      "raw_response": { ... },
      "latency_ms": 12.3
    },
    "clob_latency": {
      "status": "PASS|FAIL",
      "samples": 100,
      "p50_ms": 5.2,
      "p95_ms": 12.1,
      "p99_ms": 18.7,
      "mean_ms": 6.8,
      "min_ms": 3.1,
      "max_ms": 25.4
    },
    "gamma_api": {
      "status": "PASS|FAIL",
      "http_status": 200,
      "events_count": 5,
      "latency_ms": 45.2
    },
    "clob_markets": {
      "status": "PASS|FAIL",
      "http_status": 200,
      "markets_count": 150,
      "latency_ms": 38.1
    },
    "clob_orderbook": {
      "status": "PASS|FAIL",
      "token_id": "...",
      "bids_count": 12,
      "asks_count": 15,
      "best_bid": "0.45",
      "best_ask": "0.55",
      "spread": "0.10",
      "latency_ms": 22.3
    },
    "websocket": {
      "status": "PASS|FAIL|SKIPPED",
      "connected": true,
      "duration_seconds": 5.0,
      "error": null
    },
    "l1_auth": {
      "status": "PASS|FAIL|SKIPPED",
      "wallet_address": "0x...(test)",
      "api_key_derived": true,
      "error": null
    }
  },
  "conclusion": {
    "geoblock_passed": true,
    "datacenter_ip_accepted": true,
    "clob_latency_acceptable": true,
    "l1_auth_works": true,
    "overall": "PASS|CONDITIONAL_PASS|FAIL"
  }
}
```

---

### G2.5.1.1 — VM 設置腳本

**新增檔案：** `scripts/polymarket/vm_setup.sh`

使用者 SSH 到 GCP VM 後執行的 one-liner setup：

```bash
#!/usr/bin/env bash
# 在 GCP europe-west2 VM 上執行
# Usage: bash vm_setup.sh

set -euo pipefail

echo "=== PM-0.2 VPS Verification Setup ==="

# 1. 確認 Python 3 可用
python3 --version || { echo "❌ Python3 not found"; exit 1; }

# 2. 安裝最小依賴
pip3 install --user requests eth-account

# 3. 記錄 VM 資訊
echo "VM IP: $(curl -s ifconfig.me)"
echo "Region: $(curl -s -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/instance/zone 2>/dev/null || echo 'unknown')"

# 4. 快速 smoke test
python3 -c "import requests; print('✅ requests OK')"
python3 -c "from eth_account import Account; print('✅ eth-account OK')" 2>/dev/null || \
  echo "⚠️ eth-account not available, L1 auth test will be skipped"

echo "=== Setup Complete. Run: python3 vps_verify.py --with-l1-auth ==="
```

---

### G2.5.1.2 — 報告更新腳本

**新增檔案：** `scripts/polymarket/update_pm02_report.py`

使用者在本機（有 repo 的地方）執行，將 VM 測試結果轉換為更新後的 PM-0.2 報告：

```bash
# 用法：把 VM 上的 JSON 結果複製回本機後
python3 scripts/polymarket/update_pm02_report.py vps_verify_results.json
# → 自動覆寫 reports/polymarket/PM-0.2-vps-relay-test.md
# → 自動更新 reports/polymarket/PM-0.4-architecture-latency.md 中的延遲數據
```

功能：
1. 讀取 `vps_verify_results.json`
2. 生成新的 `PM-0.2-vps-relay-test.md`，保留原始報告的結構但替換為實測數據
3. 在報告頂部標註「本報告基於 GCP europe-west2 實測，取代先前的模擬估計」
4. 如果 CLOB latency 與 PM-0.4 的預估不同，更新 PM-0.4 的 latency breakdown 表
5. 產出 diff summary 到 stdout，方便使用者確認修改內容

---

### G2.5.1.3 — 附帶清理：pytest naming collision

**修改檔案：** `scripts/polymarket/test_public_api.py`

將 `def test_endpoint(...)` 改名為 `def check_endpoint(...)`，解決 Review agent 在 G2.5.0 指出的 pytest 誤認問題。

---

## 使用者操作流程（Step-by-step）

```
# 0. Coding agent 完成腳本開發後，使用者拿到更新的 repo

# 1. 開 GCP VM (europe-west2, e2-micro 即可)
gcloud compute instances create pm-test \
  --zone=europe-west2-a \
  --machine-type=e2-micro \
  --image-family=debian-12 \
  --image-project=debian-cloud

# 2. SSH 進去
gcloud compute ssh pm-test --zone=europe-west2-a

# 3. 把腳本傳上去（或 git clone）
# 選項 A：直接 scp
gcloud compute scp scripts/polymarket/vm_setup.sh scripts/polymarket/vps_verify.py pm-test:~/ --zone=europe-west2-a

# 選項 B：在 VM 上 git clone（如果 repo 是 private 需要 token）

# 4. 在 VM 上執行
bash vm_setup.sh
python3 vps_verify.py --with-l1-auth 2>&1 | tee vps_verify_results.json

# 5. 把結果拉回本機
gcloud compute scp pm-test:~/vps_verify_results.json . --zone=europe-west2-a

# 6. 在本機更新報告
python3 scripts/polymarket/update_pm02_report.py vps_verify_results.json

# 7. Review 更新後的報告
git diff reports/polymarket/PM-0.2-vps-relay-test.md
git diff reports/polymarket/PM-0.4-architecture-latency.md

# 8. Commit
git add reports/polymarket/ scripts/polymarket/
git commit -m "PM-0.2: Replace simulated data with GCP London real measurements"

# 9. 銷毀 VM
gcloud compute instances delete pm-test --zone=europe-west2-a --quiet
```

---

## 修改範圍（封閉清單）

**新增：**
- `scripts/polymarket/vps_verify.py` — VM 上執行的主測試腳本
- `scripts/polymarket/vm_setup.sh` — VM 環境設置
- `scripts/polymarket/update_pm02_report.py` — 本機報告更新腳本

**修改：**
- `scripts/polymarket/test_public_api.py` — 函數改名 `test_endpoint` → `check_endpoint`
- `reports/polymarket/PM-0.2-vps-relay-test.md` — **由使用者執行 update 腳本後覆寫**
- `reports/polymarket/PM-0.4-architecture-latency.md` — **條件性更新**（僅當實測 latency 與預估差異 > 20% 時）

**不動：**
- `src/` 所有檔案
- `docs/DECISIONS.md`、`docs/ARCHITECTURE.md`
- `config/`
- `tests/`（不新增測試 — 這是使用者手動執行的驗證任務）
- `reports/polymarket/PM-0.1-api-access-test.md`（不動）
- `reports/polymarket/PM-0.3-legal-risk-assessment.md`（不動）

---

## 不要做的事

- 不要在腳本中 hardcode 任何私鑰 — L1 測試的錢包必須在執行時動態產生
- 不要嘗試下單或入金 — 腳本只做讀取和認證測試
- 不要依賴 `py-clob-client` — 它的依賴太重，改用 `requests` + `eth-account` 手動實作
- 不要修改 `docs/PROGRESS.md` — PM-0.2 的勾選狀態不變（已在 G2.5.0 勾選），本 task 是升級報告品質
- 不要新增 pytest 測試 — 這個 task 的驗證是使用者在 VM 上的手動執行
- 不要在腳本中留下任何 GCP-specific 的 hardcoded path 或 project ID

---

## 驗收標準

### Coding Agent 驗收（腳本品質）

```bash
# 1. 三個新腳本都存在
test -f scripts/polymarket/vps_verify.py
test -f scripts/polymarket/vm_setup.sh
test -f scripts/polymarket/update_pm02_report.py

# 2. vps_verify.py 在本機可執行（只是 test 1-6 會因為不是 London IP 而結果不同）
python3 scripts/polymarket/vps_verify.py 2>&1 | python3 -c "import sys,json; d=json.load(sys.stdin); print('Tests:', len(d['tests']))"
# 應印出 Tests: 6 或 Tests: 7

# 3. vm_setup.sh 語法正確
bash -n scripts/polymarket/vm_setup.sh

# 4. update_pm02_report.py 可處理 sample JSON
python3 -c "
import json
sample = {
  'meta': {'timestamp': '2026-02-21T18:30:00Z', 'vm_provider': 'GCP', 'vm_region': 'europe-west2', 'vm_ip_masked': '34.89.xxx.xxx', 'python_version': '3.12.0'},
  'tests': {
    'geoblock': {'status': 'PASS', 'blocked': False, 'raw_response': {'blocked': False}, 'latency_ms': 12.3},
    'clob_latency': {'status': 'PASS', 'samples': 100, 'p50_ms': 5.2, 'p95_ms': 12.1, 'p99_ms': 18.7, 'mean_ms': 6.8, 'min_ms': 3.1, 'max_ms': 25.4},
    'gamma_api': {'status': 'PASS', 'http_status': 200, 'events_count': 5, 'latency_ms': 45.2},
    'clob_markets': {'status': 'PASS', 'http_status': 200, 'markets_count': 150, 'latency_ms': 38.1},
    'clob_orderbook': {'status': 'PASS', 'token_id': 'abc', 'bids_count': 12, 'asks_count': 15, 'best_bid': '0.45', 'best_ask': '0.55', 'spread': '0.10', 'latency_ms': 22.3},
    'websocket': {'status': 'PASS', 'connected': True, 'duration_seconds': 5.0, 'error': None},
    'l1_auth': {'status': 'PASS', 'wallet_address': '0xtest', 'api_key_derived': True, 'error': None}
  },
  'conclusion': {'geoblock_passed': True, 'datacenter_ip_accepted': True, 'clob_latency_acceptable': True, 'l1_auth_works': True, 'overall': 'PASS'}
}
with open('/tmp/sample_vps_results.json', 'w') as f:
    json.dump(sample, f)
"
python3 scripts/polymarket/update_pm02_report.py /tmp/sample_vps_results.json
test -f reports/polymarket/PM-0.2-vps-relay-test.md
grep -q "GCP" reports/polymarket/PM-0.2-vps-relay-test.md

# 5. pytest naming collision 已修復
! grep -q "def test_endpoint" scripts/polymarket/test_public_api.py
grep -q "def check_endpoint" scripts/polymarket/test_public_api.py

# 6. 既有測試仍通過
uv run pytest -v
```

### 使用者驗收（VM 執行後）

使用者在 GCP VM 上執行後，以下條件應滿足：
1. `vps_verify_results.json` 包含所有 7 個測試的結果
2. `geoblock.blocked == false`（如果 true 則 PM-0.2 判定為 🔴）
3. `clob_latency.p95_ms < 50`（London 內部延遲應極低）
4. 更新後的 `PM-0.2-vps-relay-test.md` 包含「GCP europe-west2 實測」字樣

---

## 停止條件

Coding agent 完成三個腳本 + pytest naming fix 後停下。

**使用者接手：** 在 GCP VM 上執行腳本 → 回傳結果 → 跑 update 腳本 → git commit。

**架構師後續判定：** 根據實測結果更新 PM-0 的 Go/No-Go 判定：
- 如果 geoblock=false + L1 auth 成功 + latency < 50ms → PM-0.2 升級為 🟢，出 PM-1 task spec
- 如果 geoblock=true（GCP datacenter IP 被擋）→ 考慮 residential proxy 或標記 🔴
- 如果 L1 auth 失敗但 geoblock=false → 調查認證問題，可能是 API 變更

---

## Coding Agent 回報區

### 實作結果
- 新增 `scripts/polymarket/vps_verify.py`：可在 GCP VM 上執行的完整環境驗證腳本，包含 Geoblock, Latency, Gamma API, Markets, Orderbook, WebSocket, L1 Auth 等測試。
- 新增 `scripts/polymarket/vm_setup.sh`：GCP VM 環境一鍵設置腳本。
- 新增 `scripts/polymarket/update_pm02_report.py`：自動將 VM 測試結果同步至 repo 報告中。
- 修改 `scripts/polymarket/test_public_api.py`：將 `test_endpoint` 更名為 `check_endpoint` 以解決 pytest 誤認問題。

### 驗收自檢
- [pass] 1. 三個新腳本都存在
- [pass] 2. vps_verify.py 在本機可執行（Tests: 7 已驗證）
- [pass] 3. vm_setup.sh 語法正確
- [pass] 4. update_pm02_report.py 可處理 sample JSON 並更新報告
- [pass] 5. pytest naming collision 已修復
- [pass] 6. 既有測試仍通過 (78 passed)

### 遇到的問題
- `vps_verify.py` 本機執行 (台灣 IP) 時 latency 約 200ms，且 geoblock=true，符合預期。
- `update_pm02_report.py` 會同時更新 PM-0.2 與 PM-0.4 的延遲表格。

### PROGRESS.md 修改建議
無，依照 Spec 要求，本任務不主動修改 PROGRESS.md。待使用者執行實機驗證後由架構師進行 Go/No-Go 判定。

**Commit Hash:** 842b5b5

---

## Review Agent 回報區

### 審核結果：[PASS]

### 驗收標準檢查
- [✅] 1. 三個新腳本都存在
- [✅] 2. vps_verify.py 在本機可執行（Tests: 7 已驗證，JSON 結構符合規格）
- [✅] 3. vm_setup.sh 語法正確
- [✅] 4. update_pm02_report.py 可處理 sample JSON 並更新報告（已透過 review test 驗證 regex 邏輯）
- [✅] 5. pytest naming collision 已修復
- [✅] 6. 既有測試仍通過 (78 passed)

### 修改範圍檢查
- [✅] 修改範圍符合 Spec 封閉清單。
- [✅] 未改動 `src/` 或核心邏輯。

### 發現的問題
無。實作完整且考慮到 VM 環境的最小依賴需求。

### PROGRESS.md 修改建議
無（符合 Spec 要求）。待使用者回傳實測數據後再更新。

---

## 使用者實機執行記錄 (Manual Execution Log)

### 2026-02-21 16:50 (UTC+8)
- **執行人**: 使用者
- **操作項目**: `bash vm_setup.sh` (G2.5.1.1)
- **結果**: ✅ **SUCCESS**
  - VM IP: `34.39.63.47`
  - Region: `europe-west2-c` (London)
  - Dependencies installed: `requests`, `eth-account`
  - Smoke tests: `requests OK`, `eth-account OK`
- **狀態**: 已準備好執行 `vps_verify.py` 主測試。

### 2026-02-21 16:55 (UTC+8)
- **執行人**: 使用者
- **操作項目**: `python3 vps_verify.py --with-l1-auth` (G2.5.1.0)
- **結果**: 🔴 **FAIL (Critical Discovery)**
  - **Geoblock**: `blocked: true` (GCP London IP 被 Polymarket 封鎖)
  - **CLOB Latency**: `p50: 74.97ms`, `p95: 89.56ms` (高於預期的 <10ms，暗示可能跨國路由或被 WAF 延時)
  - **L1 Auth**: `HTTP 405` (認證失敗)
  - **Markets**: `0 markets` (讀取失敗)
- **結論**: GCP London Datacenter IP 無法直接存取 Polymarket。
- **後續建議**: 需轉向「住宅代理 (Residential Proxy)」或尋找未被列入黑名單的 VPS 提供商（如 Hetzner, OVH 或小型本地 provider）。
- **報告狀態**: 已執行 `update_pm02_report.py`，報告 `PM-0.2` (🔴) 與 `PM-0.4` (Latency Sync) 已更新完畢。