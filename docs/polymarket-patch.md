# Polymarket Feasibility Study — 研究調查計畫 v2

> **目的：** 在正式轉移開發重心之前，透過系統性的實證調查確認 Polymarket 5m/15m BTC 市場是否存在可操作的獲利機會。
> **原則：** 先確認能不能用，再收資料，最後做結論。每個調查項目都有明確的「需要回答的問題」和「可執行的驗收標準」。
> **產出：** 每個 Study 完成後產出一份 `reports/polymarket/PM-X.Y-*.json` 或 `.md` 報告，作為後續決策依據。
> **版本：** v2（2026-02-20）— 新增 PM-0 存取可行性 gate，根據最新監管資訊修訂全文

---

## 建議插入 PROGRESS.md 的位置與結構

在 Gate 2 Phase 2 之後、Gate 3 之前，新增一個獨立的 section：

---

## Polymarket Feasibility Study (Gate 2.5)

**狀態：** ⏳ PROPOSED — 待架構師核可後啟動

**動機：** Polymarket 提供完整 CLOB API，解決 Binance EC 無 API 的自動化瓶頸。動態賠率創造方向預測以外的獲利維度。但台灣被列為 close-only 限制地區，需要先解決存取問題再評估 edge 是否可操作。

**關鍵背景（2026-02 調查結果）：**
- 台灣在 Polymarket 的限制等級為 **close-only**（可關倉、不可開倉），非完全封鎖
- CLOB API `/order` 端點會校驗 IP，從受限地區提交的訂單會被直接拒絕
- Public read-only API（Gamma API、order book 查詢）的 geoblock 狀態尚未確認
- 5m BTC prediction market 已於 2026 年 2 月上線，使用 Chainlink oracle 自動結算
- 台灣曾在 2024 年起訴一名使用 Polymarket 下注政治選舉的用戶（約 $530 USD）

**設計原則：**
- PM-0 是 blocker gate：不通過則整個調查終止
- 純調查研究，不寫交易邏輯
- 所有 data collector 腳本放在 `scripts/polymarket/`
- 所有報告放在 `reports/polymarket/`
- 不修改現有 Binance EC 系統的任何程式碼

**Gate 2.5 推進流程：**
```
PM-0: Access & Legal Feasibility（BLOCKER）
  - [ ] PM-0.1: Public API 存取測試（台灣 IP）
  - [ ] PM-0.2: VPS Relay 可行性測試
  - [ ] PM-0.3: 台灣法規風險評估
  - [ ] PM-0.4: E2E Architecture Latency
  → Go/No-Go 決策點（由架構師判定）

PM-1 ~ PM-7:（PM-0 通過後才展開）
  - [ ] PM-1: Market Structure & Lifecycle
  - [ ] PM-2: Price Feed 行為模式
  - [ ] PM-4: Fee Structure 完整拆解
  - [ ] PM-5: Market Implied Probability Calibration
  - [ ] PM-3: Order Book Depth & Liquidity
  - [ ] PM-6: 獲利模式可行性
  - [ ] PM-7: Engineering Integration Plan

Gate 2.5 完成條件（全部 Study 完成後由架構師判定）：
  - [ ] PM-0 ~ PM-7 全部產出報告
  - [ ] 架構師根據報告決定：🟢 正式轉移 / 🟡 部分整合 / 🔴 放棄
```

---

## PM-0：Access & Legal Feasibility（BLOCKER）

> **這是整個調查的 gate-keeper。PM-0 不通過，PM-1 到 PM-10 全部不用做。**

### 技術背景：Polymarket 的三層存取架構

```
Layer 1: Public Read API（Gamma API + CLOB public endpoints）
  → 拉市場數據、order book、歷史價格
  → 不需要錢包、不需要認證
  → geoblock 狀態：❓ 未知，需測試

Layer 2: CLOB Trading API（下單、撤單、查倉位）
  → 需要 Polygon 錢包 + EIP-712 簽名 + API credentials
  → geoblock 狀態：✅ 已確認會擋（官方文件明確記載）

Layer 3: On-chain Smart Contract（直接與 CTF 合約交互）
  → 只需要 Polygon RPC + 錢包私鑰
  → 合約層無法做 IP 檢查，但 CLOB 是 off-chain 撮合
  → 不能用來做 price discovery，只能做 split/merge/redeem
  → 僅作為緊急資金退出路徑
```

**含義：**
- Layer 1 如果通 → PM-1 到 PM-5 的純調查任務可在台灣直接做，成本極低
- Layer 2 一定被擋 → 交易必須透過非受限地區的 VPS 中繼
- Layer 3 不是可行的交易路徑，但提供資產安全的底線保障

---

### PM-0.1：Public API 存取測試（台灣 IP）

**需要回答的問題：**
1. 從台灣 IP 能否正常呼叫 Gamma API（`https://gamma-api.polymarket.com`）？
2. 從台灣 IP 能否呼叫 CLOB public endpoints（`https://clob.polymarket.com/markets`, `/book` 等）？
3. RTDS WebSocket（即時價格流）能否從台灣連線？
4. `https://polymarket.com/api/geoblock` 端點對台灣 IP 回傳什麼？
5. `py-clob-client` 的 Level 0（無認證）方法是否可用？

**方法：**
```bash
# 1. Geoblock 端點確認
curl -s "https://polymarket.com/api/geoblock" | python -m json.tool

# 2. Gamma API 測試（市場列表）
curl -s "https://gamma-api.polymarket.com/events?active=true&closed=false&limit=5" \
  -w "\n%{http_code}\n" | tail -20

# 3. CLOB public endpoint 測試（市場資料）
curl -s "https://clob.polymarket.com/markets" -w "\n%{http_code}\n" | head -c 500

# 4. py-clob-client Level 0 測試
pip install py-clob-client
python -c "
from py_clob_client.client import ClobClient
client = ClobClient('https://clob.polymarket.com')
print('OK:', client.get_ok())
print('Time:', client.get_server_time())
"

# 5. WebSocket 連線測試
python -c "
import asyncio, websockets, json
async def test():
    try:
        async with websockets.connect('wss://ws-subscriptions-clob.polymarket.com/ws/market') as ws:
            print('WS connected')
            # 嘗試訂閱一個 BTC 5m market
            await asyncio.sleep(2)
            print('WS stable for 2s')
    except Exception as e:
        print(f'WS failed: {e}')
asyncio.run(test())
"
```

**驗收標準：**
- 產出 `reports/polymarket/PM-0.1-api-access-test.md`
- 記錄每個端點的：HTTP status code、response headers（特別注意 `x-geoblock` 或類似 header）、response body 前 500 chars
- 結論分為三種：
  - 🟢 **完全可存取** — 所有 public endpoint 正常回應
  - 🟡 **部分可存取** — 明確列出哪些端點被擋、哪些暢通
  - 🔴 **完全被擋** — 所有端點返回 403/地區限制

**影響評估：**
| PM-0.1 結果 | 對後續調查的影響 |
|---|---|
| 🟢 全通 | PM-1~PM-5 可在台灣直接執行，零額外成本 |
| 🟡 部分通 | 可用的端點在台灣做，被擋的端點用 VPS |
| 🔴 全擋 | 所有數據收集都需要透過 VPS，成本增加但不致命 |

---

### PM-0.2：VPS Relay 可行性測試

**前提：** PM-0.1 完成（無論結果如何都要做這步，因為 Layer 2 一定需要 VPS）

**需要回答的問題：**
1. 從歐洲 datacenter VPS 呼叫 `https://polymarket.com/api/geoblock`，回傳 `blocked: false`？
2. 在 VPS 上能否成功安裝 `py-clob-client` 並完成 Level 0 測試？
3. 在 VPS 上能否成功建立 L1 認證（wallet signing → derive API key）？
4. 在 VPS 上能否成功建立 L2 認證（HMAC signature → 查餘額/下單）？
5. VPS 到 Polymarket CLOB server（London eu-west-2）的 RTT latency？
6. Datacenter IP 是否被 Polymarket 偵測並拒絕？（某些平台會封鎖已知 datacenter IP 段）

**方法：**
- 租一台歐洲 VPS（建議優先級）：
  1. **Hetzner Amsterdam**（€3.79/月，離 London 最近）
  2. **DigitalOcean Amsterdam**（$6/月，備選）
  3. 如果 datacenter IP 被擋：測試 residential proxy（如 Bright Data），但成本更高
- 安裝 Python 3.12 + `py-clob-client`
- 建立一個全新的 Polygon 錢包（測試用，不入金）
- 執行完整的認證流程
- 測量 latency：

```bash
# Latency 測量（在 VPS 上執行）
# 1. CLOB API RTT
for i in $(seq 1 100); do
  curl -s -o /dev/null -w "%{time_total}\n" "https://clob.polymarket.com/time"
done | awk '{sum+=$1; n++; a[n]=$1} END {
  asort(a); 
  print "p50:", a[int(n*0.5)]*1000, "ms";
  print "p95:", a[int(n*0.95)]*1000, "ms";
  print "p99:", a[int(n*0.99)]*1000, "ms";
  print "mean:", sum/n*1000, "ms"
}'

# 2. Geoblock 驗證
curl -s "https://polymarket.com/api/geoblock" | python -m json.tool

# 3. L1 認證測試
python -c "
from py_clob_client.client import ClobClient
import os

client = ClobClient(
    'https://clob.polymarket.com',
    key='<test-private-key>',
    chain_id=137
)
try:
    creds = client.create_or_derive_api_creds()
    print('L1 auth SUCCESS:', creds)
except Exception as e:
    print('L1 auth FAILED:', e)
"
```

**驗收標準：**
- 產出 `reports/polymarket/PM-0.2-vps-relay-test.md`
- 包含：
  - VPS provider、地點、IP 地址（脫敏）、IP 類型（datacenter/residential）
  - Geoblock endpoint 回傳的完整 JSON
  - L1/L2 認證結果（成功/失敗 + 錯誤訊息）
  - Latency 統計表（p50/p95/p99/mean，100 次取樣）
- 結論：
  - 🟢 **Datacenter VPS 可行** — geoblock 通過、認證成功、latency < 50ms
  - 🟡 **需要 residential proxy** — datacenter IP 被擋但 residential 通過
  - 🔴 **VPS 方案不可行** — 所有 IP 類型都被擋或認證失敗

**不要做的事：**
- 不要入金或嘗試下單（這步只測認證，不測交易）
- 不要使用你的主要加密錢包（建立新的測試錢包）
- 不要在 VPS 上存放任何敏感資訊（測試完即銷毀）

---

### PM-0.3：台灣法規風險評估

**需要回答的問題：**
1. 台灣 2024 年起訴 Polymarket 用戶的案例，具體是什麼罪名？判決結果？
2. 台灣刑法第 266 條（賭博罪）的構成要件是什麼？「在公共場所或公眾得出入之場所賭博」是否涵蓋線上平台？
3. 純加密貨幣價格預測（非政治/體育事件）在台灣法律框架下是否被歸類為「賭博」？是否有判例區分？
4. 金管會對「加密貨幣衍生品交易」的監管立場？是否有明確禁止？
5. 透過 VPS 存取被限制的境外金融平台，在台灣法律下是否構成獨立罪名？
6. 小額（<$500 USDT）的實質執法風險評估 — 過去是否有針對小額加密貨幣交易的執法案例？

**方法：**
- 搜尋台灣「刑法 賭博罪 線上」相關判例
- 搜尋台灣「Polymarket 起訴」的具體報導和判決書
- 搜尋金管會「虛擬通貨 衍生品 預測市場」相關公告
- 比較：政治事件預測 vs 金融資產價格預測 的法律定位差異
- 參考台灣對 Binance Event Contract 的監管態度（如果有）

**驗收標準：**
- 產出 `reports/polymarket/PM-0.3-legal-risk-assessment.md`
- 包含：
  - 相關法條引用（刑法 266、268 條，及其他適用法規）
  - 2024 起訴案的具體資訊（罪名、金額、結果）
  - 政治博弈 vs 金融預測的法律區分分析
  - 風險矩陣：

| 行為 | 法規風險 | 執法機率 | 備註 |
|------|---------|---------|------|
| 用台灣 IP 瀏覽 Polymarket（view-only）| — | — | — |
| 透過 VPS 在 Polymarket 交易 BTC 方向預測 | — | — | — |
| 透過 VPS 在 Polymarket 交易政治事件 | — | — | — |
| 使用 Binance Event Contract（現況）| — | — | 作為參照基準 |

- 結論：「法規風險：🟢 低 / 🟡 中 / 🔴 高」附具體理由

**重要提醒：** 這不是正式法律意見。如果結論為 🟡 或 🔴，建議在正式投入前諮詢台灣律師。

---

### PM-0.4：End-to-End Architecture Latency 評估

**前提：** PM-0.1 ~ PM-0.3 結果均非 🔴

**需要回答的問題：**
- 如果模型推理在台灣本地 GPU，交易執行在歐洲 VPS，整個鏈路的 end-to-end latency 是多少？
- 這個 latency 對不同策略的影響？

**目標架構：**
```
Binance WS（台灣收）
  → 模型推理（台灣 GPU，< 1s）
  → 交易信號 SSH/API → VPS（歐洲 Amsterdam）
  → CLOB API → Polymarket CLOB（London）
  → 撮合 + Polygon 結算
```

**方法：**
```bash
# 1. 台灣 → VPS RTT
ping -c 100 <vps-ip> | tail -1
# 預期：~200-250ms（台灣到歐洲典型值）

# 2. VPS → Polymarket CLOB RTT（PM-0.2 已測，直接引用）

# 3. 模擬完整鏈路
# 在台灣本地：
time curl -s "https://<vps-ip>:8080/relay-test" 
# VPS 上的 relay-test endpoint 會呼叫 Polymarket API 並回傳結果
```

**Latency Budget 計算：**

| 環節 | 預估延遲 | 備註 |
|------|---------|------|
| Binance WS → 本地接收 | ~50ms | 現有系統已測 |
| 模型推理 | < 1000ms | DECISIONS.md 約束 |
| 台灣 → 歐洲 VPS | ~200-250ms | SSH tunnel 或 HTTP relay |
| VPS → CLOB API 下單 | ~10-30ms | PM-0.2 測得 |
| CLOB 撮合 | ~50-100ms | 取決於流動性 |
| **總計** | **~1.3-1.5s** | — |

**策略適用性分析：**

| 策略類型 | 所需延遲 | 1.5s 是否可接受 |
|---------|---------|----------------|
| 方向預測 + 有利價格入場（PM-6.1）| 秒級即可 | ✅ 充裕 |
| 中途對沖鎖利（PM-6.2）| 秒級即可 | ✅ 充裕 |
| Binance price lead（PM-6.5）| 毫秒級 | ❌ 可能不足 |
| Market making（PM-6.3）| 毫秒級 | ❌ 不可行 |

**驗收標準：**
- 產出 `reports/polymarket/PM-0.4-architecture-latency.md`
- 包含實測的 latency breakdown（不是估算）
- 包含上述策略適用性分析表
- 結論：「對 [策略 X, Y] latency 可接受 / 對 [策略 Z] 不可行」

---

### PM-0 Go/No-Go 決策矩陣

| PM-0.1 | PM-0.2 | PM-0.3 | PM-0.4 | 決定 |
|--------|--------|--------|--------|------|
| 🟢 public API 通 | 🟢 datacenter VPS 通 | 🟢 法規低風險 | ✅ 可接受 | **🟢 GO** — 全速推進 PM-1~PM-7 |
| 🟢 public API 通 | 🟡 需 residential proxy | 🟢 法規低風險 | ✅ 可接受 | **🟡 CONDITIONAL** — 評估 proxy 成本後決定 |
| 🔴 public API 被擋 | 🟢 VPS 通 | 🟢 法規低風險 | ✅ 可接受 | **🟡 CONDITIONAL** — 所有調查需透過 VPS，成本增加 |
| 任意 | 🔴 VPS 全被擋 | 任意 | — | **🔴 STOP** — 僅做 read-only 調查（PM-1/5），放棄交易路徑 |
| 任意 | 任意 | 🔴 法規高風險 | — | **🔴 STOP** — 不值得冒法律風險 |
| 任意 | 任意 | 任意 | ❌ 全不可行 | **🔴 STOP** — latency 無法支撐任何有意義的策略 |

---

## PM-1：Market Structure & Lifecycle 調查

**前提：** PM-0 通過

**需要回答的問題：**
1. 5m market 的完整生命週期是什麼？何時開放交易、何時停止接單、何時結算？
2. 相鄰的 5m market 之間是否有 gap（例如 3:00-3:05 結算後，3:05-3:10 何時可以開始交易）？
3. Market 的 condition_id / token_id 是如何生成的？能否提前預測下一個 market 的 ID？
4. "Up" 的結算條件是 `>=`（含平盤）還是 `>`（嚴格高於）？— **這對模型 label 設計至關重要**
   - 我們現有的 `labeling.py` 將平盤視為 lose，如果 Polymarket 將 `>=` 視為 Up win，label 邏輯需要修改
5. 15m / 1h / 4h / 1d market 的結構是否相同？各自的交易窗口是什麼？
6. 5m market 是何時上線的？目前是否仍在 beta？是否有下架風險？
7. Chainlink BTC/USD oracle 的結算精度是多少位小數？

**方法：**
- 用 Gamma API 抓取最近 24h 的所有 BTC 5m/15m market 的 metadata
- 記錄每個 market 的 creation_time, start_time, end_time, resolution_time
- 檢查 resolution source（Chainlink BTC/USD data stream）的具體文件
- 比對 Polymarket 的結算價 vs Binance 的 close price（取同一時間戳）

**驗收標準：**
- 產出 `reports/polymarket/PM-1-market-structure.md`
- 包含完整的 lifecycle timeline diagram（ASCII 或 mermaid）
- 回答上述所有 7 個問題，每個有明確的數據支撐
- 特別標註：結算條件（`>=` vs `>`）的明確結論

---

## PM-2：Price Feed 行為模式調查

**前提：** PM-1 完成

### PM-2.1：Chainlink Oracle 靜態規格分析

**需要回答的問題：**
1. Chainlink BTC/USD oracle feed 的更新頻率（heartbeat interval）是多少？
2. Deviation threshold 是多少？（即價格變動多少才觸發更新）
3. Chainlink 在 Polygon 上是否有獨立的 feed，還是從 Ethereum bridge 過來的？
4. 是否有歷史 API 可以回拉 Chainlink 價格數據？能回拉多久？
5. Polymarket 用的是哪個具體的 Chainlink aggregator contract？

**方法：**
- 查閱 Chainlink data feeds 文件
- 找到 Polymarket 使用的 BTC/USD feed 的 Polygon contract 地址
- 從 contract 讀取 `latestRoundData()` 的 roundId、timestamp、answer
- 如果有歷史 API，測試回拉 7 天的數據

**驗收標準：**
- 產出 `reports/polymarket/PM-2.1-chainlink-specs.md`
- 包含：heartbeat_interval, deviation_threshold, aggregator_address, update_frequency
- 結論：「是否可回測 / 需要自行收集前瞻性數據」

### PM-2.2：Binance vs Chainlink 動態偏差分析

**前提：** PM-2.1 完成確認更新頻率

**需要回答的問題：**
1. Chainlink BTC/USD feed 與 Binance BTC/USDT spot price 之間的平均延遲差異？
2. 在 BTC 劇烈波動時（>0.5% / 5min），兩個 price feed 的偏差會放大到多少？
3. 在 5m window 結算時刻（:00, :05, :10...），兩個 price 的差異分布？
4. 用 Binance 數據訓練的模型預測 Chainlink 結算，預期方向判斷偏差率是多少？

**方法：**
- 同時記錄 Binance BTC/USDT WebSocket 和 Chainlink oracle 的價格
- 記錄頻率：Binance 每 100ms、Chainlink 每次 on-chain update
- 持續收集 48 小時以上，涵蓋至少一次 >1% 的 5 分鐘波動
- 計算：mean lag, max lag, correlation, divergence distribution
- 特別分析：每 5 分鐘的結算時刻（:00, :05, :10...）的偏差

**驗收標準：**
- 產出 `reports/polymarket/PM-2.2-price-feed-analysis.json`
- 包含統計指標：mean_lag_ms, p95_lag_ms, max_divergence_usd, correlation_coefficient
- 包含：在結算時刻的方向判斷一致率（Binance close > open 與 Chainlink close > open 是否一致）
- 結論：「用 Binance 數據訓練的模型預測 Chainlink 結算，方向一致率為 X%，不一致的 case 中偏差中位數為 $Y」

---

## PM-4：Fee Structure 完整拆解

**前提：** PM-1 完成（需要了解 market structure）

> **注意：** 優先級提前至 PM-3 之前，因為 fee 是純文件分析，不需要收集數據，且結論直接影響是否值得做 PM-3。

**需要回答的問題：**
1. Polymarket 的 fee 公式 `feeQuote = baseRate × min(price, 1-price) × size` 中 `baseRate` 的精確值是多少？
2. Maker order（limit order sit on book）是否真的完全免費？Maker rebate 的計算方式和回饋比例？
3. 在 p=0.30, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70 各點的 taker fee 精確金額？
4. Polygon gas fee 在不同網路負載下的範圍？每筆交易的固定成本？
5. 買入後在結算前賣出（提前平倉）的 fee 結構是否相同？
6. 在 $10 / $50 / $100 的 position size 下，total cost（fee + estimated spread）是多少？

**關鍵差異對比 — Binance EC vs Polymarket：**

| 維度 | Binance EC | Polymarket |
|------|-----------|------------|
| 費用模式 | 隱含在 payout ratio（1.80/1.85）| 明確的 taker fee + spread |
| 盈虧結構 | 贏：bet × payout，輸：-bet | 贏：size × (1 - entry_price) - fee，輸：-size × entry_price - fee |
| Breakeven | 固定（55.56% / 54.05%）| 動態（取決於 entry price + fee）|
| 入場成本 | 固定（bet amount）| 動態（price × size + fee）|

**方法：**
- 從 Polymarket docs 和 CLOB Introduction 提取 fee 公式和 baseRate
- 從 `py-clob-client` 原始碼確認 fee 計算邏輯
- 計算完整的 cost table
- 與 Binance EC 的等效成本做交叉比較

**驗收標準：**
- 產出 `reports/polymarket/PM-4-fee-analysis.md`
- 包含完整的 cost table：

| Entry Price | Position | Taker Fee | Est. Spread Cost (from PM-3) | Gas | Total Cost | Breakeven Edge | Binance EC 等效成本 |
|-------------|----------|-----------|------------------------------|-----|------------|----------------|-------------------|
| 0.30 | $50 | ... | (待 PM-3) | ... | ... | ... | ... |
| 0.40 | $50 | ... | (待 PM-3) | ... | ... | ... | ... |
| 0.45 | $50 | ... | (待 PM-3) | ... | ... | ... | ... |
| 0.50 | $50 | ... | (待 PM-3) | ... | ... | ... | ... |
| 0.55 | $50 | ... | (待 PM-3) | ... | ... | ... | ... |
| 0.60 | $50 | ... | (待 PM-3) | ... | ... | ... | ... |
| 0.70 | $50 | ... | (待 PM-3) | ... | ... | ... | ... |

- 結論：「Polymarket 的 total cost 在 price 範圍 X-Y 內 [高於/低於/等同] Binance EC」

---

## PM-5：Market Implied Probability Calibration 調查

**前提：** PM-1 完成（需要理解 market lifecycle）

> **注意：** 優先級提前至 PM-3 之前。這是最有可能發現可操作 edge 的調查，且可以用 Gamma API 歷史數據完成，不需要即時 order book 數據。

**需要回答的問題：**
1. 5m market 的 market price 是否是 true probability 的無偏估計？（calibration curve）
2. 在 target price 附近震盪時，market price 是否系統性地 overreact？（overreaction 頻率與幅度）
3. Market 在不同時段（亞洲時段 / 歐洲時段 / 美國時段）的 calibration 是否有差異？
4. 開盤初期（前 60 秒）的 pricing 是否比中後段更不準確？
5. 高波動期 vs 低波動期的 calibration 差異？
6. 我們的 lgbm_v2 / catboost_v1 模型的 directional confidence 與 market price 的差值分布如何？

**方法：**
- 收集 200+ 個已結算的 5m market 的完整 price history + outcome
- 建 calibration curve：將 market price 分 bucket（0-10%, 10-20%, ..., 90-100%），計算每個 bucket 的 actual win rate
- 特別分析「price 在 40-60% 區間震盪」的 market subset
- 按時段/波動率分組做 sub-group analysis
- 將我們現有模型的預測（用同一時段的 Binance 數據跑推理）與 market price 對比

**驗收標準：**
- 產出 `reports/polymarket/PM-5-calibration-analysis.json`
- 包含 calibration curve 的 bucket 數據和 Brier score
- 包含時段/波動率的 sub-group 分析
- 包含 model_confidence vs market_price 的差值分布
- 結論三選一：
  - 🟢 「market price 在 X 範圍內系統性高估/低估 Y%，可操作」
  - 🟡 「存在小幅偏差但可能不足以覆蓋 fee」
  - 🔴 「calibration 良好，無系統性偏差，純方向預測無額外 edge」

---

## PM-3：Order Book Depth & Liquidity 調查

**前提：** PM-4 完成（需要知道 fee structure 才能計算 slippage 的實際影響）

> **注意：** 排在 PM-4 和 PM-5 之後。如果 PM-4 顯示 fee 過高或 PM-5 顯示無 calibration edge，PM-3 的優先級可以再降低。

**需要回答的問題：**
1. 5m market 在不同生命階段（剛開盤 / 中段 / 接近結算）的 order book depth 如何變化？
2. 在 $10 / $50 / $100 / $500 的 order size 下，預期 slippage 各是多少？
3. Bid-ask spread 的典型範圍是多少？在 target price 附近震盪時 spread 如何變化？
4. 流動性主要由 market maker bot 提供還是散戶？（觀察 order 的 size 分布和更新頻率）
5. 15m market 的流動性是否顯著優於 5m？如果是，15m 是否是更好的起步選擇？
6. Maker order 的 fill rate 是多少？（掛單但不一定成交的風險）

**方法：**
- 每 1 秒記錄一次 order book snapshot（至少 5 levels 深度）for 連續 48h
- 分時段統計：開盤後 0-60s / 60-180s / 180-240s / 最後 60s
- 對比 5m 和 15m market 的 depth
- 計算不同 order size 的模擬 fill price（walk the book）
- 分析 order 的 size 分布（是否集中在特定金額，暗示 bot 活動）

**驗收標準：**
- 產出 `reports/polymarket/PM-3-liquidity-analysis.json`
- 包含：avg_spread, depth_at_$50, depth_at_$100, slippage_at_$50, slippage_at_$100（分時段）
- 包含：5m vs 15m 的 depth 對比
- 包含：maker order fill rate（如果 PM-0.2 允許實際掛單的話）
- 結論：「在 $X 以下的 order size，slippage 可控在 Y% 以內」

---

## PM-6：獲利模式可行性調查

**前提：** PM-2 ~ PM-5 全部完成

**需要回答的問題：**

### PM-6.1：方向預測 + 有利價格入場（最核心）

1. 我們的 lgbm_v2 / catboost_v1 模型的 confidence output 與 Polymarket market price 的差值分布如何？
2. 當 model_confidence - market_price > X% 時，historical win rate 是多少？
3. 用 limit order（maker，0 fee）入場的 fill rate 是多少？
4. 從 model 預測到 order fill 的平均延遲是多少？
5. 綜合 fee + slippage + fill rate，在最佳操作價格範圍內的 expected PnL per trade？

### PM-6.2：持倉中途反向對沖（鎖定利潤）

1. 買入 "Up" 後，market price 震盪到有利方向的機率和幅度？
2. 在多少比例的 market 中，可以在結算前以 > entry_price 賣出？
3. 提前平倉的 average profit 和 hold-to-settlement 的 average profit 比較？
4. 提前平倉需要吃掉 spread + taker fee，什麼幅度的價格變動才能 cover 這個成本？

### PM-6.3：雙邊 Market Making（探索性）

1. 在 5m market 上做 market making 的理論 PnL 模型：spread capture - adverse selection loss
2. Adverse selection 風險有多大？（知情交易者在 BTC 價格突然變動後吃掉你的掛單）
3. Inventory risk 在 5 分鐘窗口內有多大？
4. **latency 限制：** 從台灣經 VPS 的 ~1.5s 延遲是否讓 market making 完全不可行？

### PM-6.4：Cross-timeframe 策略

1. 5m market 和 15m market 的 price 是否有 lead-lag 關係？
2. 能否用 15m market 的 price movement 預測 5m market 的 outcome？
3. 同時在 5m 和 15m 做方向相反的 bet，是否能構造出 risk-reduced position？

### PM-6.5：Binance Spot Price Lead 策略

1. 當 Binance 即時價格在 5m window 中間突然跳動，Polymarket market price 的反應延遲是多少？
2. 在 Binance price jump > $100 的 event 中，Polymarket price 需要多少秒才能 fully reflect？
3. 反應延遲中的 edge 是否足以覆蓋 taker fee？
4. **latency 限制：** 我們的 ~1.5s E2E 延遲 vs 專業 bot 的 <100ms 延遲，是否有足夠的 edge window？

**方法：**
- PM-6.1 ~ 6.2：需要 PM-2、PM-3、PM-5 的資料作為輸入，加上用現有模型跑推理
- PM-6.3：模擬分析，用 PM-3 的 order book 資料建模，同時考慮 PM-0.4 的 latency 限制
- PM-6.4：用 Gamma API 同時收集 5m 和 15m 的 market data
- PM-6.5：用 PM-2 收集的 dual price feed 資料分析，結合 PM-0.4 的 latency budget

**驗收標準：**
- 產出 `reports/polymarket/PM-6-profitability-analysis.md`
- 每個子模式給出：

| 策略 | 預估 Edge | 預估頻率 | E[PnL/trade] | E[trades/day] | E[PnL/day] | Latency 可行？ | 建議 |
|------|----------|---------|-------------|--------------|------------|---------------|------|
| PM-6.1 | ... | ... | ... | ... | ... | ✅/❌ | ... |
| PM-6.2 | ... | ... | ... | ... | ... | ✅/❌ | ... |
| PM-6.3 | ... | ... | ... | ... | ... | ✅/❌ | ... |
| PM-6.4 | ... | ... | ... | ... | ... | ✅/❌ | ... |
| PM-6.5 | ... | ... | ... | ... | ... | ✅/❌ | ... |

- 結論：排名哪些模式最值得投入，哪些應該放棄

---

## PM-7：Engineering Integration Plan

**前提：** PM-6 結論中至少有一個 🟢 策略

> **注意：** 原始版本的 PM-7 是 API 工程可行性調查，但其中核心的 geoblock 和 latency 問題已被 PM-0 涵蓋。本修訂版將 PM-7 改為「如果決定正式整合，需要做什麼」的工程規劃。

**需要回答的問題：**
1. 我們的 Binance EC 架構中，哪些模組可以直接復用於 Polymarket？
2. 需要新增哪些模組？（Polymarket data feed、CLOB client wrapper、VPS relay service）
3. 現有的 PredictionSignal / SimulatedTrade dataclass 是否需要擴展？
4. model retrain 的 label source 是否需要從 Binance index 切換到 Chainlink？
5. 帳戶設置流程：Polygon wallet → USDC 入金 → API key → 第一筆交易的完整路徑
6. 最小交易金額是多少？（Binance EC 是 5 USDT）
7. VPS 的持續運維成本和可靠性方案

**方法：**
- 基於 PM-0 ~ PM-6 的所有資料，產出一份工程整合方案
- 包含模組圖、介面擴展提案、和與 ARCHITECTURE.md 的 diff 預覽

**驗收標準：**
- 產出 `reports/polymarket/PM-7-engineering-plan.md`
- 包含：模組復用清單、新增模組清單、介面變更提案、VPS 運維方案
- 包含：完整的 onboarding checklist（從零到第一筆交易）
- 包含：預估開發時間和 gate 結構提案
- 結論：「整合需要 X 天開發，建議以 [策略名] 為 MVP」

---

## 補充調查（如果 PM-1~7 結果正面，進一步深入）

### PM-8（條件性）：Historical Outcome 回測

**前提：** PM-2 確認 Chainlink 有歷史 API、PM-5 calibration 顯示有 edge

**需要回答的問題：**
1. 用我們既有的 lgbm_v2 / catboost_v1 模型預測 Polymarket 5m 結算結果的 directional accuracy 是多少？
2. 與預測 Binance EC 結算的 DA 相比，偏差多少？（量化 Chainlink vs Binance index 的影響）
3. 如果需要 retrain，Chainlink 歷史資料能否作為新的 label source？

### PM-9（條件性）：Competition & Adversary 分析

**前提：** PM-6 顯示有可操作的 edge

**需要回答的問題：**
1. 5m market 上有多少活躍的 bot？（觀察 order 更新的頻率和模式）
2. 主要 market maker 的 quoting 策略是什麼？（觀察他們的 bid-ask width 和 update 頻率）
3. 是否有明顯的「狙擊 bot」在 Binance price jump 後瞬間 sweep Polymarket book？
4. 我們的延遲（台灣到 Polymarket，~1.5s）相對於主要競爭者的劣勢有多大？

### PM-10（條件性）：Risk & Regulatory 深度評估

**前提：** 決定正式投入 Polymarket

**需要回答的問題：**
1. Polymarket smart contract 的安全性：audit 報告結論？歷史 exploit 事件？
2. USDC on Polygon 的 bridge risk（注意：Polymarket 已遷移至原生 USDC，bridge risk 降低）
3. 帳戶資金上限和提領限制？
4. Polymarket 如果下架 5m market，我們的資金退出路徑？
5. VPS 帳戶被偵測和凍結的風險？凍結後的資金回收路徑？

---

## 執行優先級與依賴關係

```
PM-0（Access & Legal Feasibility）— 最先，整個調查的 gate-keeper
  PM-0.1（Public API 測試）→ PM-0.2（VPS 測試）→ PM-0.3（法規）→ PM-0.4（Latency）
  → ★ Go/No-Go 決策點 ★
  ↓
PM-1（Market Structure）— 所有後續調查的基礎知識
  ↓
PM-4（Fee Structure）— 純文件分析，快速完成
  ↓（可平行）
PM-2（Price Feed）+ PM-5（Calibration）— 需要收集數據，早開始
  ↓
PM-3（Order Book Liquidity）— 需要 48h 持續收集
  ↓
PM-6（Profitability Analysis）— 依賴 PM-2 ~ PM-5 的全部資料
  ↓
PM-7（Engineering Plan）— 依賴 PM-6 結論
  ↓
PM-8/9/10（條件性）— 根據 PM-6/7 結論決定是否進行
```

**預估時間：**
- PM-0：2-3 天（VPS 租用 + 測試 + 法規調研）
- PM-1 + PM-4：1-2 天（主要是 API 探索 + 文件閱讀）
- PM-2 + PM-5：3-5 天（需要持續數據收集）
- PM-3：2-3 天（48h 收集 + 分析）
- PM-6 + PM-7：2-3 天（分析已收集的資料 + 工程規劃）
- **總計：10-16 天完成核心調查（含 PM-0）**

---

## 與現有系統的關係

**不動的部分：**
- Gate 0-2 的所有現有程式碼和基礎設施
- Binance EC 的 live pipeline 繼續運行（收集 signal data）
- 現有的 model training / backtest 系統
- DECISIONS.md、ARCHITECTURE.md（在 PM-7 之前不修改）

**可復用的部分：**
- Binance WebSocket data feed（PM-2 需要同步比較）
- SQLite 資料庫架構（PM-3 的 order book 快照可用類似 schema）
- Discord Bot notification（未來 Polymarket 訊號也走同一個 bot）
- lgbm_v2 / catboost_v1 的模型推理能力（PM-5/6.1 直接用）
- Signal Layer 的記錄機制（未來可擴展到 Polymarket signals）

**需要新增的部分：**
- `scripts/polymarket/` — 所有 data collector 腳本
- `reports/polymarket/` — 所有調查報告
- `src/btc_predictor/polymarket/` — 未來正式整合時的模組（本階段不動）

---

## 版本歷史

| 版本 | 日期 | 變更 |
|------|------|------|
| v1 | 2026-02-20 | 初版，7 個調查任務 |
| v2 | 2026-02-20 | 新增 PM-0 gate；修訂 PM-2 拆分為靜態/動態兩階段；PM-4 提前至 PM-3 之前；PM-5 提升優先級；PM-7 改為 Engineering Plan；加入 latency 限制對各策略的影響分析；更新台灣 close-only 狀態和 CLOB API geoblock 事實 |