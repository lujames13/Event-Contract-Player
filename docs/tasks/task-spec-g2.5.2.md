# Task Spec G2.5.2 — PM-0 遺留問題修復 + Tokyo 補測

<!-- status: done -->
<!-- created: 2026-02-21 -->
<!-- architect: Claude Opus (Chat Project) -->

> **Gate:** 2.5（Polymarket Feasibility Study）
> **優先級:** 🔴 High — PM-0 Go/No-Go 決策之擋路石
> **前置條件:** G2.5.1 完成，確認 GCP London 被封鎖且 Japan 可連線但 API 異常
> **執行者:** Coding agent 修正腳本 → **使用者本人**在 GCP Tokyo VM 補測 → 決定 Go/No-Go

---

## 目標

經過 G2.5.1 在 GCP London 與 Japan 的實測，我們確認：
1. GCP London (europe-west2) 被 Polymarket API `geoblock: true` 封鎖。
2. GCP Japan (asia-northeast1) `geoblock: false` 可連線，但延遲略高 (~300-500ms)。
3. **重大異常**：
   - CLOB API `/markets` 回傳 0 筆（可能需要 query parameters 如 `?limit=100` 或端點變更）。
   - L1 Auth 測試得到 `HTTP 405 Method Not Allowed`，確認 `/auth/api-key` 端點或 HTTP Method 有誤。

本任務目標：
1. **修復腳本**：由 Coding Agent 調查 Polymarket 最新 API 文件，修正 `scripts/polymarket/vps_verify.py` 中的 API 端點與請求方式。
2. **Tokyo 補測**：由使用者依據修正後的腳本在 Tokyo VM 重跑，取得完整 `markets`、`orderbook` 與 `websocket` 數據。
3. **重新判定 PM-0**：依據實測結果做最終的決策。

---

## 子任務

### G2.5.2.1 — 修復 L1 Auth 405 錯誤
**修改檔案：** `scripts/polymarket/vps_verify.py` (`test_l1_auth` 函數)
- 目前 `requests.get("https://clob.polymarket.com/auth/api-key")` 返回 405。
- 請查閱 Polymarket API 文件（如需可使用 MCP search 或 web search 工具），確認 deriving API key 的正確 Endpoint (POST/GET?)、Path 以及 Payload。
- 測試目的不是成功登入，而是**確認 IP 未被 WAF 阻擋且能觸發正確的 API 反應（例如 400 Bad Request, 401 Unauthorized，而不是 405 或 403 封鎖）**。

### G2.5.2.2 — 修復 Markets 回傳 0 筆問題
**修改檔案：** `scripts/polymarket/vps_verify.py` (`test_clob_markets` 函數)
- 目前 `requests.get("https://clob.polymarket.com/markets")` 回傳 200 但長度為 0。
- 調查是否需要加上 query params（如 `?active=true` 或 `?limit=100` 或 `next_cursor`）。
- 同時確認 Gamma API 在 Tokyo 是否可正常拿回 events。
- 從修復後的 `markets` 清單中正確抓出一個 `token_id` 以供後續的 orderbook 測試使用。

### G2.5.2.3 — 修正自動化總結邏輯 (Conclusion)
**修改檔案：** `scripts/polymarket/vps_verify.py` (`main` 函數)
- 把 `latency < 100` 的臨時限制放寬，因為如果是 Tokyo/Taiwan 連線美國主機，延遲通常會在 200-500ms 之間。將 `clob_latency_acceptable` 的標準改為 `clob_lat.get("p95_ms", 999) < 600`。
- 修改最後 `overall` 判定邏輯，只要 `geoblock_passed` 且有抓到 `markets` 資料，整體就不算 `FAIL`。

---

## 使用者操作流程（Tokyo 實測 Step-by-step）

Coding Agent 完成腳本修改後，請使用者依循以下步驟執行：

```bash
# 1. 建立 GCP Tokyo VM
gcloud compute instances create pm-test-tokyo \
  --zone=asia-northeast1-b \
  --machine-type=e2-micro \
  --image-family=debian-12 \
  --image-project=debian-cloud

# 2. 上傳修復後的腳本
gcloud compute scp scripts/polymarket/vm_setup.sh scripts/polymarket/vps_verify.py pm-test-tokyo:~/ --zone=asia-northeast1-b

# 3. SSH 連線到 VM
gcloud compute ssh pm-test-tokyo --zone=asia-northeast1-b

# 4. 執行 Setup 與測試腳本
bash vm_setup.sh
python3 vps_verify.py --with-l1-auth 2>&1 | tee vps_verify_tokyo.json

# 5. 返回本機，下載報告並更新
exit
gcloud compute scp pm-test-tokyo:~/vps_verify_tokyo.json . --zone=asia-northeast1-b
python3 scripts/polymarket/update_pm02_report.py vps_verify_tokyo.json

# 6. 清理 VM
gcloud compute instances delete pm-test-tokyo --zone=asia-northeast1-b --quiet
```

---

## 修正後的 PM-0 Go/No-Go 標準

使用者完成實測後，架構師會依據以下標準判斷：

- 如果 L1 Auth 通過 (非 403/405) + Markets 可讀 → 🟢 **GO**（後續用 Tokyo VPS 架構）
- 如果 L1 Auth 仍然失敗但 Markets 可讀 → 🟡 **CONDITIONAL**（需深入排查認證流程，可能是 API 變更或 Python ECDSA 簽名格式問題）
- 如果 Markets 仍然 = 0 → 🔴 **NO-GO**（Polymarket API 可能有針對特定區域的未公開限制，或 CLOB 徹底分離）

---

## 修改範圍（封閉清單）

- `scripts/polymarket/vps_verify.py`

*(不動其他檔案，報告更新腳本 `update_pm02_report.py` 不需更改，因為 JSON 結構不變)*

---

## 不要做的事

- 不要實作完整的 `py-clob-client` 邏輯，`vps_verify.py` 的重點在於用最乾淨的 `requests` 來測試存取權。
- 不要跑任何真實的下單指令或提交具備金錢價值的交易。
- 不要在本次 Task 修改 `docs/PROGRESS.md`，這個交由 Architect 評估實測數據後處理。

---

## Coding Agent 回報區

### 實作內容概述
已修改 `scripts/polymarket/vps_verify.py` 腳本：
1. **修復 Markets 讀取 0 筆問題：** 發現 `/markets` API 實際回傳了包含 `"data"` 鍵的 JSON dictionary（而非直接是 list），因此調整了解析邏輯以從 `"data"` 中提取 markets list。
2. **修復 L1 Auth 405 錯誤：** 查閱了 `py-clob-client` 文件，將認證 API Endpoint 改為 `POST /api-key/create-or-derive`，以此測試 IP 在 authenticated route 下的 WAF 反應 (預期 400/401)。
3. **優化延遲與判定標準：** 在 `main()` 中將 `clob_latency_acceptable` 的 p95 閾值從 100 增強為 600ms。同時更新了 `overall` 判定邏輯，當 `geoblock_passed` 為 true 且抓到 `markets` 資料時，即可給予非 FAIL 判定。

### 驗收自檢
- [x] 修改 `/markets` 取得 `data["data"]` 陣列機制（本地測實驗證為 1000 筆資料）。
- [x] 把 L1 Auth 連線改為 POST `https://clob.polymarket.com/api-key/create-or-derive`。
- [x] 更新 `clob_latency_acceptable` 的判定門檻到 `< 600`。
- [x] 成功在本地執行 `vps_verify.py`，JSON 產出完整，未發生 Exception 或 TypeError，整體邏輯正確。

### 回饋與發現
本地執行因台灣 IP block 而使得 `overall: FAIL`，且 `API/Orderbook` 不可訪問符合預期。請在 GCP Tokyo 機器進行最終實機測試。

---

## Review Agent 回報區

### 審核結果
[PASS]

### 檢查清單
- [x] L1 Auth 改為使用 POST `https://clob.polymarket.com/api-key/create-or-derive`，實測回傳 401，代表通過 WAF 防禦並進入認證邏輯。
- [x] `/markets` 取得 `data["data"]` 陣列機制修復，回傳 >0。
- [x] 成功通過 GCP Tokyo VM 實機驗證。

---

## 實機執行記錄與決策 (Architect Desk)

### 2026-02-21 21:45 (UTC+8) - GCP Tokyo VM 實測
- **執行人**: 使用者
- **結果**: 🟢 **SUCCESS**
  - **Geoblock**: `blocked: false` (日本 GCP Datacenter 未被限)
  - **CLOB Latency**: `p50: 304.84ms`, `p95: 331.39ms`
  - **L1 Auth**: `HTTP 401` (成功探通 Auth 邏輯)
  - **Markets**: `1000 markets` (成功探通)
- **結論**: PM-0.2 結論更新為可透過 GCP Asia-Northeast1 進行資料連線。延遲 300ms 左右對於 10m/30m/60m 等級的趨勢交易（非高頻套利）可接受。

### PM-0 Go/No-Go 最終判定
經過數週的評估與實測：
- PM-0.1 台灣 IP API 連線不被封鎖。
- PM-0.2 GCP Asia-Northeast1 (Tokyo) Datacenter IP 連線不被封鎖。
- PM-0.3 法律層面的操作與法規限制在風險評估可接受範圍，且技術面上不影響串接層。
- PM-0.4 Architecture Latency 雖提升至 300ms 級別，但不影響我們的模型週率。
**判定結果：🟢 GO**
我們將繼續推進 PM-1 到 PM-7 的研究。

(任務結束，本 Spec 可視為 `status: done`)
