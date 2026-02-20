# Task Spec G2.5.4 — PM-2.1 Chainlink Oracle 靜態規格 + PM-5 Market Calibration 分析

<!-- status: review -->
<!-- created: 2026-02-22 -->
<!-- architect: Claude Opus (Chat Project) -->

> **Gate:** 2.5（Polymarket Feasibility Study）
> **優先級:** 🔴 High — PM-5 是判斷 Polymarket 是否存在可操作 edge 的核心調查
> **前置條件:** G2.5.3 完成（PM-1 Market Structure + PM-4 Fee Structure 已產出）

---

## 目標

完成 `docs/polymarket-patch.md` 中定義的 **PM-2.1（Chainlink Oracle 靜態規格分析）** 和 **PM-5（Market Implied Probability Calibration）** 兩項調查。

合併理由：
1. PM-2.1 是純文件研究 + 合約查詢，產出量小但為 PM-5 提供關鍵上下文（oracle 精度、更新頻率）
2. PM-5 是整個 Polymarket 調查中**最可能產出 Go/No-Go 信號的調查**——如果 market price 已經是 well-calibrated，則純方向預測沒有額外 edge，整個 Polymarket 方向可能需要重新評估
3. 兩者都可從台灣 IP 直接用 Gamma API 完成，不需要 VPS 或持續數據收集

**這個 task 的結論直接影響後續路徑：**
- PM-5 🟢（存在系統性 mispricing）→ 繼續推進 PM-2.2 + PM-3 + PM-6
- PM-5 🔴（market well-calibrated）→ 重新評估是否值得繼續投入 Polymarket

---

## 前置調查結論摘要（供 coding agent 參考）

**PM-0 實測結論：**
- 台灣 IP：Gamma API + CLOB read-only 暢通
- GCP Tokyo：geoblock=false，CLOB p95 ~331ms
- 架構：資料採集走台灣本地，交易走 GCP Tokyo

**PM-1 關鍵發現：**
- 5m market 每 5 分鐘整點滾動，相鄰 market 無 gap
- 結算條件：`>=`（含平盤 = Up），與 Binance EC 的 `>`（平盤 = Lose）不同
- Slug 格式：`btc-updown-5m-<unix_timestamp>`，可提前推算
- Chainlink Oracle 結算精度：8-10 位小數
- `priceToBeat` 在開盤時即鎖定，公開於 `eventMetadata`
- Tag ID：`1312`（Crypto Prices category）

**PM-4 關鍵發現：**
- Taker fee：`feeQuote = baseRate × min(p, 1-p) × size`
- Maker：免費 + daily rebate
- Polymarket taker fee 在全價格區間低於 Binance EC 等效成本
- 但 total cost 尚未定論（缺 spread cost，待 PM-3）

---

## 子任務

### G2.5.4.1 — PM-2.1：Chainlink Oracle 靜態規格分析

**新增檔案：**
- `scripts/polymarket/investigate_chainlink.py` — Oracle 規格調查腳本
- `reports/polymarket/PM-2.1-chainlink-specs.md` — 調查報告

**需要回答的 5 個問題：**

1. **Chainlink BTC/USD oracle feed 的更新頻率（heartbeat interval）是多少？**
2. **Deviation threshold 是多少？**（價格變動多少 % 才觸發 on-chain 更新）
3. **Chainlink 在 Polygon 上是否有獨立的 feed，還是從 Ethereum bridge 過來的？**
   - PM-1 已確認 Polymarket 使用 "Chainlink BTC/USD Real-time Data Stream"
   - 需要區分：傳統 Chainlink Price Feed（on-chain aggregator）vs Data Streams（off-chain 低延遲 pull-based）
   - 如果是 Data Streams，更新頻率可能遠高於傳統 feed
4. **是否有歷史 API 可以回拉 Chainlink 價格數據？能回拉多久？**
   - 如果有 → PM-8（Historical Outcome 回測）可行
   - 如果沒有 → 需要自行收集前瞻性數據
5. **Polymarket 用的是哪個具體的 Chainlink aggregator contract 或 Data Stream ID？**

**調查方法：**

```python
# 1. Web 搜尋 Polymarket 結算機制的官方文件
#    - 搜尋 "Polymarket Chainlink oracle BTC settlement"
#    - 搜尋 "Polymarket UMA oracle crypto prices"
#    - 檢查 Polymarket docs / blog 是否有 oracle 機制說明

# 2. 從 PM-1 已收集的 market metadata 中提取 oracle 資訊
#    - eventMetadata 中的 resolution_source
#    - market description 中的 oracle 引用

# 3. 查詢 Chainlink 官方文件
#    - Polygon BTC/USD Price Feed: https://data.chain.link/feeds/polygon/mainnet/btc-usd
#    - Chainlink Data Streams 文件
#    - 找到 aggregator contract address

# 4. 如果找到 contract address，用 Polygon RPC 讀取
#    - latestRoundData() → 取得最新價格、roundId、timestamp
#    - 計算相鄰 round 的時間間隔 → 推導實際更新頻率
#    - 注意：使用公共 RPC（如 https://polygon-rpc.com）即可，不需要付費節點

# 5. 調查歷史數據可用性
#    - Chainlink 官方是否有 historical API？
#    - 第三方（如 DeFiLlama、Dune Analytics）是否有 Chainlink 歷史數據？
#    - 如果需要 on-chain 歷史，是否可用 event log 回拉？
```

**報告結構要求：**

| 參數 | 值 | 來源 |
|------|-----|------|
| Feed Type | Price Feed / Data Stream | 文件 |
| Heartbeat Interval | X 秒 | 合約讀取 / 文件 |
| Deviation Threshold | X% | 文件 |
| Polygon Contract Address | 0x... | 文件 / 鏈上驗證 |
| Update Frequency (實測) | ~X 秒 | 合約讀取 |
| 結算精度 | X 位小數 | PM-1 已確認 8-10 位 |
| 歷史數據可用性 | 是/否，回溯深度 | API 測試 |

**結論必須明確回答：**「是否可用 Chainlink 歷史數據進行回測？如果否，需要自行收集多少天的前瞻性數據才有意義？」

---

### G2.5.4.2 — PM-5：Market Implied Probability Calibration 分析

**新增檔案：**
- `scripts/polymarket/analyze_calibration.py` — 校準分析腳本（注意：與現有 `scripts/analyze_calibration.py` 是不同的腳本，一個是 Binance EC signal 校準，一個是 Polymarket market price 校準）
- `reports/polymarket/PM-5-calibration-analysis.md` — 分析報告

**需要回答的 6 個問題：**

1. **5m market 的 market price 是否是 true probability 的無偏估計？**（calibration curve）
2. **在 target price 附近震盪時，market price 是否系統性地 overreact？**
3. **不同時段（亞洲 / 歐洲 / 美國）的 calibration 是否有差異？**
4. **開盤初期（前 60 秒）的 pricing 是否比中後段更不準確？**
5. **高波動期 vs 低波動期的 calibration 差異？**
6. **我們的 lgbm_v2 / catboost_v1 模型 confidence 與 market price 的差值分布如何？**

> **問題 6 的重要限制：** coding agent 大概率沒辦法直接跑我們的模型推理（需要載入 trained model + 對齊 Binance 數據時間戳）。替代方案：跳過問題 6，改為在報告中標註「需要在 PM-8 中用現有模型跑推理後補充」。PM-5 聚焦在 market price 本身的 calibration quality。

**數據收集方法：**

```python
# Step 1：收集已結算的 5m market 數據
#   - 用 Gamma API 批量拉取最近 7-14 天的已結算 btc-updown-5m markets
#   - GET https://gamma-api.polymarket.com/events?tag_id=1312&closed=true&limit=100&offset=0
#   - 逐頁翻取，目標 ≥ 500 個已結算 market（7 天 × 288 個/天 = 2016 個）
#   - 對每個 market 記錄：
#     - question, slug, condition_id
#     - outcomePrices (最終 market price，但注意這可能是結算後的 1.00/0.00)
#     - tokens[0].token_id, tokens[1].token_id (Up / Down)
#     - end_date_iso (結算時間)
#     - 結算結果 (Up won / Down won)

# Step 2：收集每個 market 的交易期間 price history
#   方法 A（首選）：使用 CLOB timeseries endpoint（如果存在）
#     - GET https://clob.polymarket.com/prices-history?market=<condition_id>&interval=1m
#     - 或使用 Gamma API 的 price history endpoint
#   方法 B（備選）：使用 Gamma API 的 market-level outcomePrices
#     - 如果只有最終價格沒有時間序列，則 calibration 分析只能用「結算前最後一個可觀測 price」
#     - 這仍然有價值，但無法回答問題 4（開盤初期 vs 中後段）
#   方法 C（如果 A/B 都沒有時間序列）：使用 CLOB midpoint 端點做即時快照
#     - 這需要持續收集，不適合本 task，記錄為「待 PM-2.2 補充」

# Step 3：建構 Calibration Curve
#   - 將 market price 分 10 個 bucket：[0-10%), [10-20%), ..., [90-100%]
#   - 對每個 bucket：
#     - 計算該 bucket 中所有 market 的 actual win rate（Up won 的比例）
#     - 計算 bucket 內 market 數量（sample size）
#     - 計算 95% confidence interval
#   - 計算整體 Brier Score：BS = (1/N) × Σ(forecast_i - outcome_i)²
#   - Perfect calibration: bucket midpoint = actual win rate

# Step 4：Sub-group Analysis
#   - 按時段分組：
#     - 亞洲時段 (00:00-08:00 UTC)
#     - 歐洲時段 (08:00-16:00 UTC)  
#     - 美國時段 (16:00-00:00 UTC)
#   - 按波動率分組（用結算窗口內的 BTC 價格變動幅度）：
#     - 低波動：|close - open| / open < 0.1%
#     - 中波動：0.1% - 0.3%
#     - 高波動：> 0.3%
#   - 按 market price 區間分組（重點關注 40-60% 範圍）：
#     - 「接近確定」區間：0-20% 或 80-100%
#     - 「不確定」區間：40-60%

# Step 5：可操作性分析
#   - 找到 calibration 偏差最大的 bucket
#   - 計算：如果在該 bucket 反向下注，expected edge 是多少？
#   - 結合 PM-4 的 fee 數據，計算 net edge（扣除 taker fee 後）
#   - 特別關注：market price 在 45-55% 區間的 actual win rate
#     - 如果 actual win rate 顯著偏離 50%，代表 market 在「不確定」時有系統性偏差
```

**報告結構要求：**

必須包含以下內容：

**1. 數據概覽：**
- 收集的 market 總數、時間範圍、Up vs Down 的整體勝率

**2. Calibration Curve 表格：**

| Market Price Bucket | N (markets) | Actual Up Win Rate | Expected (bucket midpoint) | Deviation | 95% CI |
|---------------------|-------------|-------------------|---------------------------|-----------|--------|
| 0-10% | ... | ... | 5% | ... | ... |
| 10-20% | ... | ... | 15% | ... | ... |
| ... | ... | ... | ... | ... | ... |
| 90-100% | ... | ... | 95% | ... | ... |

**3. Brier Score：**
- Overall Brier Score
- 與 baseline（naive 50% forecast）的比較

**4. Sub-group Analysis：**
- 按時段的 calibration deviation 表
- 按波動率的 calibration deviation 表
- 40-60% 區間的深入分析

**5. 可操作性評估：**
- 最大 calibration deviation 的 bucket + 扣除 PM-4 taker fee 後的 net edge
- 如果用 maker order（0 fee），edge 是否足夠？

**6. 結論（三選一，必須明確）：**
- 🟢 「market price 在 [具體範圍] 系統性 [高估/低估] [具體百分比]，扣除 fee 後仍有 [X%] net edge，可操作」
- 🟡 「存在 [具體] 偏差但扣除 fee 後 edge 極薄（< 1%），需要 maker order 才可能獲利」
- 🔴 「calibration 良好（Brier Score < 0.25），無系統性偏差超過 fee 成本，純方向預測無額外 edge」

---

### G2.5.4.3 — PROGRESS.md 更新

**修改檔案：** `docs/PROGRESS.md`

將以下兩項勾選為完成：
```
- [x] PM-2: Price Feed 行為模式  ← 注意：只勾 PM-2.1 已完成的部分
```

**修改方式：** 將 PROGRESS.md 中的 PM-2 拆分為兩行：
```
- [x] PM-2.1: Chainlink Oracle 靜態規格
- [ ] PM-2.2: Binance vs Chainlink 動態偏差分析（需 48h 數據收集）
- [x] PM-5: Market Implied Probability Calibration
```

---

## 修改範圍（封閉清單）

**新增：**
- `scripts/polymarket/investigate_chainlink.py`
- `scripts/polymarket/analyze_calibration.py`（注意命名：polymarket 目錄下的，不是根目錄的）
- `reports/polymarket/PM-2.1-chainlink-specs.md`
- `reports/polymarket/PM-5-calibration-analysis.md`

**修改：**
- `docs/PROGRESS.md` — 拆分 PM-2 為 PM-2.1 / PM-2.2 並勾選完成項

**不動：**
- `src/` 所有檔案
- `docs/DECISIONS.md`
- `docs/ARCHITECTURE.md`
- `config/`
- `tests/`
- 現有的 `reports/polymarket/PM-0.*`、`PM-1-*`、`PM-4-*` 報告
- 現有的 `scripts/polymarket/` 已有腳本（vps_verify.py, collect_market_structure.py 等）
- `scripts/analyze_calibration.py`（這是 Binance EC 的校準工具，不要動）

---

## 不要做的事

- **不要入金或嘗試下單** — 純讀取 API + 文件調查
- **不要安裝 `py-clob-client` 或 `web3`** — 如果需要讀取 Polygon 合約數據，用 `requests` 呼叫公共 RPC 的 `eth_call` 即可
- **不要嘗試跑我們的 lgbm_v2 / catboost_v1 模型** — 問題 6 標註為「待 PM-8 補充」即可
- **不要收集即時數據**（如持續抓 order book）— 那是 PM-3 / PM-2.2 的工作
- **不要修改任何 Binance EC 系統的程式碼**
- **不要連接 GCP VM** — 所有操作從台灣 IP 直接執行
- **不要修改或覆蓋 `scripts/analyze_calibration.py`**（根目錄的是 Binance EC 用的）

---

## 技術注意事項

### Gamma API 分頁
PM-5 需要 ≥ 500 個已結算 market。Gamma API 每次最多回傳 ~100 筆，需要用 `offset` 分頁：
```python
all_markets = []
offset = 0
while True:
    resp = requests.get(
        "https://gamma-api.polymarket.com/events",
        params={"tag_id": 1312, "closed": "true", "limit": 100, "offset": offset}
    )
    events = resp.json()
    if not events:
        break
    # 從 events 中過濾出 5m BTC markets
    for event in events:
        if "btc-updown-5m" in event.get("slug", ""):
            all_markets.append(event)
    offset += 100
```

### Market Price 取得方式
已結算的 market 的 `outcomePrices` 可能已經是 `"1.00"` / `"0.00"`（結算後重置）。需要找到**結算前的最後交易價格**。可能的來源：
- `Gamma API /markets/<id>` 的 `bestBid` / `bestAsk`（可能已清零）
- `Gamma API /events` 的 `outcomePrices`（可能反映結算後狀態）
- CLOB API 的 `GET /prices-history`（如果存在）

**如果無法取得結算前的 market price 時間序列：**
- 記錄這個限制
- 嘗試用 `volume` × `outcomePrices`（如果 outcomePrices 反映的是加權平均交易價）
- 作為 fallback，收集未來 24h 的 live market 數據做 forward-looking calibration
- 在報告中明確標註數據來源和限制

### Polygon RPC 公共端點
讀取 Chainlink 合約不需要付費 RPC：
```python
# 公共 RPC（免費，有 rate limit）
POLYGON_RPC = "https://polygon-rpc.com"
# 或 Alchemy/Infura 免費 tier（如果公共 RPC 太慢）
```

### 波動率計算
PM-5 需要按波動率分組，但 market metadata 中沒有直接的波動率數據。可用的 proxy：
- 從 market 的 `priceToBeat`（開盤 BTC 價格）和結算結果推斷方向，但無法推斷幅度
- 如果 Chainlink 有歷史 API（PM-2.1 結論），可以回拉對應時段的 BTC 價格計算波動率
- 如果沒有，用 Binance OHLCV 數據（我們已有）作為 proxy：`SELECT * FROM ohlcv WHERE timestamp BETWEEN market_start AND market_end`
- **注意時區對齊**：Polymarket market 的 start/end 是 UTC

---

## 驗收標準

```bash
# 1. 報告檔案存在
test -f reports/polymarket/PM-2.1-chainlink-specs.md
test -f reports/polymarket/PM-5-calibration-analysis.md

# 2. 腳本檔案存在且可執行
test -f scripts/polymarket/investigate_chainlink.py
test -f scripts/polymarket/analyze_calibration.py
python3 scripts/polymarket/investigate_chainlink.py --help 2>&1 | grep -qi "usage\|help\|error"
python3 scripts/polymarket/analyze_calibration.py --help 2>&1 | grep -qi "usage\|help\|error"

# 3. PM-2.1 報告包含關鍵參數
grep -qi "heartbeat" reports/polymarket/PM-2.1-chainlink-specs.md
grep -qi "deviation" reports/polymarket/PM-2.1-chainlink-specs.md
grep -qi "polygon" reports/polymarket/PM-2.1-chainlink-specs.md
grep -qi "歷史\|history\|historical" reports/polymarket/PM-2.1-chainlink-specs.md

# 4. PM-5 報告包含 calibration 分析
grep -qi "brier" reports/polymarket/PM-5-calibration-analysis.md
grep -qi "calibration" reports/polymarket/PM-5-calibration-analysis.md
grep -qi "bucket" reports/polymarket/PM-5-calibration-analysis.md
# 結論必須是 🟢 / 🟡 / 🔴 三選一
grep -qE "🟢|🟡|🔴" reports/polymarket/PM-5-calibration-analysis.md

# 5. PROGRESS.md 更新
grep "\[x\].*PM-2.1" docs/PROGRESS.md
grep "\[x\].*PM-5" docs/PROGRESS.md

# 6. 既有測試仍通過
uv run pytest -v
```

---

## 停止條件

### PM-5 數據取得失敗的處理

如果 Gamma API 無法提供已結算 market 的**結算前 market price**（outcomePrices 已被重置為 1.00/0.00），則：

1. **先嘗試替代端點**：CLOB `/prices-history`、Gamma `/markets` 的 `bestBid`/`bestAsk`
2. **如果所有替代都失敗**：
   - PM-5 報告標註為 `⏸ BLOCKED — 缺乏歷史 market price 數據`
   - 在報告中記錄嘗試過的所有端點和回傳結果
   - 提出替代方案：啟動 24h forward-looking 數據收集腳本（可與 PM-2.2 合併）
   - 完成 PM-2.1 並正常交付

---

## Coding Agent 回報區

### 實作結果
- 新增 `scripts/polymarket/investigate_chainlink.py`：成功透過 Polygon RPC 查詢 Aggregator V3 合約，確認 Heartbeat 與 Deviation 參數。
- 新增 `scripts/polymarket/analyze_calibration.py`：批量拉取 500 個已結算 5m BTC 市場，並對齊 CLOB 歷史價格進行校準分析。
- 產出 `reports/polymarket/PM-2.1-chainlink-specs.md`：紀錄 Oracle 規格與 Data Streams 機制。
- 產出 `reports/polymarket/PM-5-calibration-analysis.md`：發現 5m 市場在 40-60% 區間極度高效（校準偏差 < 1.2%），對單純方向性預測提出警示。
- 更新 `docs/PROGRESS.md`：拆分 PM-2 並勾選完成項。

### 驗收自檢
- [x] 報告檔案存在
- [x] 腳本檔案存在且可執行
- [x] PM-2.1 報告包含關鍵參數 (heartbeat, deviation, polygon)
- [x] PM-5 報告包含 calibration 分析 (brier, bucket, 🔴 結論)
- [x] PROGRESS.md 更新
- [x] 既有測試仍通過 (已執行 pytest)

### 遇到的問題
- **Gamma API 分頁限制**：初始嘗試一次拉取 500 個 event 失敗，已修復為使用 `offset` 循環拉取。
- **CLOB Price History 延遲**：部分 token_id 的歷史數據拉取較慢，已在腳本中加入進度 Log。
- **Pandas Categorical Subtraction**：在分析腳本中遇到 `TypeError`，已改用手動 binning 並轉換為 float 解決。

### PROGRESS.md 修改建議
- 無。目前的拆分 (PM-2.1 / PM-2.2) 已能準確反映進度。

**Commit Hash:** 64c784b

---

## Review Agent 回報區

### 審核結果：[PASS / FAIL / PASS WITH NOTES]

### 驗收標準檢查
<!-- 逐條 ✅/❌ -->

### 修改範圍檢查
<!-- git diff --name-only 的結果是否在範圍內 -->

### 發現的問題
<!-- 具體問題描述 -->

### PROGRESS.md 修改建議
<!-- 如有 -->