# Polymarket Migration Plan — 從 Binance EC 轉移至 Polymarket

> **日期：** 2026-02-22
> **版本：** v2.0
> **狀態：** DRAFT — 待使用者確認後執行
> **決策背景：** 完成 PM-0 ~ PM-6 調查後，決定以 Polymarket 5m BTC 市場為主要交易標的
> **v2 變更：** Binance 系統不是「廢棄」而是「收攏整理」，保留未來復用可能

---

## 1. 遷移動機與決策依據

### 為什麼離開 Binance EC

| 問題 | 嚴重性 | 說明 |
|------|--------|------|
| 無官方 API | 🔴 Critical | 自動下單必須走 Android emulator UI 自動化，脆弱且不可靠 |
| 固定賠率 | 🟡 Medium | Payout ratio 1.80/1.85 固定，breakeven 高達 54-56% |
| 結算條件不利 | 🟡 Medium | `>` 嚴格大於，平盤算輸 |

### 為什麼選擇 Polymarket

| 優勢 | 說明 |
|------|------|
| 完整 CLOB API | REST + WebSocket，可完全自動化交易 |
| Maker 零手續費 | Breakeven 接近 50%，edge 門檻大幅降低 |
| 動態賠率 | Order book 價格反映市場共識，可利用 model alpha |
| 結算條件 `>=` | 平盤算 Up，對我方模型稍有利 |
| Chainlink Oracle 結算 | 透明可驗證，8 位小數精度 |

### PM 調查關鍵結論

- **PM-0（Access）**：🟢 台灣 IP 可讀 API，GCP Tokyo 可交易，latency p95 ~331ms
- **PM-5（Calibration）**：🔴 市場高度校準，Brier Score 0.2489 ≈ baseline，純 mispricing 套利不可行
- **PM-6（Model Alpha）**：🟡 現有 10m/60m 模型有 timeframe mismatch，但 alpha > 5% 區間有正 edge；需訓練專門的 5m 模型
- **核心路徑**：訓練 Polymarket-native 多 timeframe 模型 → Maker order → 低 breakeven → 正 PnL

---

## 2. 四份核心文件的修改方向

### 2.1 DECISIONS.md — 修改清單

原則：**Binance EC 段落加 `[SUSPENDED]` 標註但不刪除，新增 Polymarket 段落。**

#### 需要新增的段落

**§8. 平台遷移決策**

```markdown
## 8. 平台遷移決策（2026-02-XX）

| 決策 | 值 | Rationale |
|------|-----|-----------|
| 主要交易平台 | Polymarket（5m BTC market） | 完整 CLOB API 解決自動化瓶頸；maker 零手續費大幅降低 breakeven |
| Binance EC 狀態 | ⏸ SUSPENDED — 停止開發，程式碼收攏保留 | 無 API 自動化為硬性限制，但模型與基礎設施保留復用可能 |
| 資料源保留 | Binance WebSocket 1m OHLCV 繼續作為共用特徵源 | 模型訓練仍需高頻價格數據，Polymarket 本身非價格數據源 |
```

**§9. Polymarket 交易規格**

```markdown
## 9. Polymarket 交易規格

| 參數 | 值 | 說明 |
|------|-----|------|
| 可用市場 | 5m / 15m / 1h / 4h / 1d BTC Up/Down | 全部使用 Chainlink Oracle 結算 |
| 初始聚焦 | 5m + 15m | PM-6 顯示短 timeframe 交易機會最密集，但不排除其他 |
| 結算條件 | `>=`（含平盤 = Up） | 與 Binance EC 的 `>` 不同，所有 timeframe 共用 |
| Oracle | Chainlink Data Streams (BTC/USD) | 亞秒級更新，8 位小數精度 |
| Taker fee | `baseRate × min(p, 1-p) × size` | p=0.50 時 effective ~3.12% |
| Maker fee | 0（免費 + daily rebate） | 核心優勢：breakeven ≈ 50% |
| 交易模式 | 優先 Maker order | Taker 僅作為 fallback |
| 交易執行地 | GCP asia-northeast1 (Tokyo) VPS | 台灣 IP 被限制交易（close-only） |
| 資料採集地 | 台灣本地 | Gamma API + CLOB read-only 暢通 |

**Polymarket timeframe 列表：**

| Timeframe | Market 頻率 | 每日機會數 | 說明 |
|-----------|------------|-----------|------|
| 5m | 每 5 分鐘 | 288 | 最高頻，流動性待驗證 |
| 15m | 每 15 分鐘 | 96 | PM-3-lite 已收集初步數據 |
| 1h | 每小時 | 24 | 與 Binance EC 60m 可比較 |
| 4h | 每 4 小時 | 6 | 低頻但可能有更穩定 edge |
| 1d | 每日 | 1 | 與 Binance EC 1440m 可比較 |

**盈虧平衡勝率（所有 timeframe 共用）：**
- Maker order：~50.0%（無手續費）
- Taker order（p=0.50）：~51.56%（含 fee）
```

**§10. Polymarket 風控參數**

```markdown
## 10. Polymarket 風控參數

| 參數 | 值 | Rationale |
|------|-----|-----------|
| 單筆 order size | $10 - $100 | 依 alpha 大小線性映射 |
| 最低 alpha 閾值 | 待 5m 模型訓練後校準 | 現有 10m 模型的 alpha 分佈不適用 |
| 每日最大虧損 | $200 | Polymarket 允許更大 position size |
| 每日最大交易數 | 100 | 5m market = 每天 288 個 opportunity |
| Max concurrent open orders | 3 | 防止過度曝險 |
```

#### 需要標註的段落

- **§2（Event Contract 規格）**→ 加上 `[SUSPENDED — Binance EC]`
- **§3（信心度閾值）**→ 加上 `[SUSPENDED — Binance EC]`
- **§4（風控參數）**→ 加上 `[SUSPENDED — Binance EC]`

#### 保持不變的段落

- §1（Runtime 環境）— GPU/SQLite/Python/uv 全部不變
- §5（模擬倉要求）— 邏輯適用兩個平台
- §6（設計原則）— 通用
- §7（數據記錄原則）— Signal Layer / Execution Layer 完全復用

---

### 2.2 ARCHITECTURE.md — 修改清單

**大幅重寫。** Binance 時期的架構描述快照到 `docs/binance/ARCHITECTURE-binance.md`，主線改為 Polymarket。

#### 系統總覽圖：重寫

```
┌─────────────────────────────────────────────────────────────┐
│                    Data Pipeline Layer                       │
│                                                             │
│  ┌──────────────────────┐  ┌─────────────────────────────┐  │
│  │ Binance WebSocket    │  │ Polymarket API              │  │
│  │ (1m OHLCV — 共用特徵) │  │ Gamma (metadata)           │  │
│  │                      │  │ CLOB (book, prices, trade)  │  │
│  └──────────┬───────────┘  └──────────┬──────────────────┘  │
│             │                         │                     │
│             ▼                         ▼                     │
│  ┌──────────────────────────────────────────────────┐       │
│  │ Unified Feature DataFrame                        │       │
│  │ OHLCV + market_price + alpha + lifecycle_stage   │       │
│  └─────────────────────┬────────────────────────────┘       │
└────────────────────────┼────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Strategy Registry (多模型並行)                   │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │ pm_v1        │ │ pm_v2        │ │ ...          │        │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘        │
│         ▼                ▼                ▼                 │
│    PredictionSignal PredictionSignal PredictionSignal        │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│               Decision & Execution Layer                    │
│  Alpha ≥ 閾值? → Maker order via CLOB API (GCP Tokyo VPS)  │
│  → SimulatedTrade / PolymarketOrder → SQLite                │
│  Order lifecycle: place → monitor fill → settlement         │
└──────────────┬──────────────────────┬───────────────────────┘
               │                      │
               ▼                      ▼
        CLI / 回測               Discord Bot
```

#### 介面契約擴展

**PredictionSignal** — 新增 Polymarket 專屬欄位：

```python
@dataclass
class PredictionSignal:
    # === 通用欄位（Binance + Polymarket 共用）===
    strategy_name: str
    timestamp: datetime
    direction: Literal["higher", "lower"]
    confidence: float
    timeframe_minutes: int
    current_price: float
    features_used: list[str]

    # === Polymarket 擴展欄位 ===
    market_slug: str | None = None
    market_price_up: float | None = None
    alpha: float | None = None
    order_type: Literal["maker", "taker"] | None = None
```

**新增 — PolymarketOrder**：

```python
@dataclass
class PolymarketOrder:
    signal_id: str
    order_id: str
    token_id: str
    side: Literal["BUY", "SELL"]
    price: float
    size: float
    order_type: Literal["GTC", "FOK", "GTD"]
    status: Literal["OPEN", "FILLED", "PARTIAL", "CANCELLED", "EXPIRED"]
    placed_at: datetime
    filled_at: datetime | None = None
    fill_price: float | None = None
    fill_size: float | None = None
```

#### SQLite Schema：新增 Polymarket 表

```sql
CREATE TABLE pm_markets (
    slug            TEXT PRIMARY KEY,
    condition_id    TEXT NOT NULL,
    up_token_id     TEXT NOT NULL,
    down_token_id   TEXT NOT NULL,
    start_time      TEXT NOT NULL,
    end_time        TEXT NOT NULL,
    price_to_beat   REAL,
    outcome         TEXT,
    close_price     REAL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE pm_orders (
    order_id        TEXT PRIMARY KEY,
    signal_id       TEXT REFERENCES prediction_signals(id),
    token_id        TEXT NOT NULL,
    side            TEXT NOT NULL,
    price           REAL NOT NULL,
    size            REAL NOT NULL,
    order_type      TEXT NOT NULL,
    status          TEXT NOT NULL,
    placed_at       TEXT NOT NULL,
    filled_at       TEXT,
    fill_price      REAL,
    fill_size       REAL,
    pnl             REAL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
```

#### 保留不變

- BaseStrategy 基類、Strategy Registry
- Signal Layer + Execution Layer 雙層模型
- `ohlcv` 表、`prediction_signals` 表、`simulated_trades` 表

---

### 2.3 PROGRESS.md — 重寫

#### 新 Gate 結構

```markdown
## [SUSPENDED] Gate 0-2: Binance EC 開發歷程

> Binance EC 系統暫停開發，程式碼收攏至 binance/ 子目錄。
> 詳細歷史記錄保留於下方，供未來復用參考。

（所有既有 Gate 0-2 內容保留不刪除）

---

## [COMPLETED] Gate 2.5: Polymarket Feasibility Study

（保留既有 PM-0 ~ PM-6 記錄）

---

## Gate 3: Polymarket MVP

**通過條件：**
- [ ] 至少 1 個 timeframe 的模型 walk-forward DA > 52%（maker breakeven + 安全邊際）
- [ ] Paper trading 200+ 筆（可跨 timeframe 合計），alpha-filtered 正 PnL
- [ ] 72 小時 pipeline 穩定運行

### 3.0 遷移與重組
- [ ] 3.0.1 核心文件遷移（DECISIONS / ARCHITECTURE / PROGRESS / constants）
- [ ] 3.0.2 目錄結構重組（Binance 收攏、Polymarket 新目錄）

### 3.1 Polymarket 基礎設施
- [ ] 3.1.1 Gamma API client + CLOB read-only client
- [ ] 3.1.2 Market lifecycle tracker（偵測當前 5m market）
- [ ] 3.1.3 Label 邏輯修改（>= 結算條件，平台參數化）
- [ ] 3.1.4 SQLite schema migration（pm_markets, pm_orders）

### 3.2 模型訓練（多 timeframe 探索）
- [ ] 3.2.1 Feature engineering（reuse Binance 1m OHLCV + PM market features，timeframe-agnostic）
- [ ] 3.2.2 pm_v1 訓練（CatBoost 基礎，>= 結算，5m/15m/1h/4h/1d 全跑）
- [ ] 3.2.3 Walk-forward 回測 × 每個 timeframe（PM 結算條件 + fee 模型）
- [ ] 3.2.4 Alpha 分析 × 每個 timeframe（model vs market price，找出最佳 timeframe-model 組合）

### 3.3 模擬交易驗證
- [ ] 3.3.1 Paper trading pipeline（signal + 模擬 maker order）
- [ ] 3.3.2 Discord Bot 適配（/predict 顯示 alpha，/stats 適配 PM PnL）
- [ ] 3.3.3 累積 200+ 筆 → 統計顯著性驗證

---

## Gate 4: Polymarket Live Trading

### 4.1 VPS 交易基礎設施
- [ ] 4.1.1 GCP Tokyo VPS 部署 + Polygon wallet + USDC 入金
- [ ] 4.1.2 CLOB API trading client（EIP-712 簽名）
- [ ] 4.1.3 VPS ↔ 本地通訊機制
### 4.2 Order Management
- [ ] 4.2.1 Maker order placement + fill monitoring
- [ ] 4.2.2 Position management + PnL settlement
### 4.3 驗證
- [ ] 4.3.1 小額實盤（$10/trade × 50 trades）
- [ ] 4.3.2 真實 vs 模擬績效對比 + slippage 分析

---

## Gate 5: 規模化
- [ ] 5.1 Position sizing 優化
- [ ] 5.2 多策略並行（pm_v2 等新模型架構）
- [ ] 5.3 Advanced order types（GTD, 動態 repricing）
```

---

### 2.4 project_constants.yaml — 修改清單

```yaml
# === 新增：Polymarket 區塊 ===
polymarket:
  timeframes: [5, 15, 60, 240, 1440]   # 所有可用 timeframe
  initial_focus: [5, 15]                # Gate 3 優先探索
  settlement_condition: ">="
  oracle: "Chainlink Data Streams (BTC/USD)"
  taker_fee_base_rate: 0.0222
  maker_fee: 0.0
  maker_rebate: true
  min_order_size: 1
  breakeven_winrate:
    maker: 0.500
    taker_at_p50: 0.5156
  vps_region: "asia-northeast1"

alpha_thresholds:                       # 每個策略 × timeframe 獨立校準
  pm_v1: null                           # 待模型訓練後填入

# === 既有 Binance 區塊加 [SUSPENDED] 標註 ===
```

---

## 3. 檔案存放結構重組

### 3.1 設計原則

核心思路：**平台分立、共用元件保持原位。**

Binance 和 Polymarket 的專屬程式碼各自收攏在對應子目錄中，共用基礎設施（strategies framework、data store、backtest engine）不動。

**不重命名 package** — `btc_predictor` 保留（預測標的仍是 BTC，且改名破壞 100+ import）。

### 3.2 目標結構

```
project/
├── docs/
│   ├── ARCHITECTURE.md              # 重寫：Polymarket 主線
│   ├── DECISIONS.md                 # 擴展：§8-10 新增，§2-4 SUSPENDED
│   ├── PROGRESS.md                  # 重寫：新 Gate 結構
│   ├── AGENTS.md                    # 更新
│   ├── binance/                     # ★ Binance 文件收攏
│   │   ├── ARCHITECTURE-binance.md  # 架構快照
│   │   └── polymarket-patch.md      # 遷移研究（歷史）
│   └── templates/
│       └── task-spec-template.md
│
├── config/
│   └── project_constants.yaml       # 擴展
│
├── src/btc_predictor/
│   ├── __init__.py
│   ├── models.py                    # 擴展 PredictionSignal + 新增 PolymarketOrder
│   │
│   ├── infrastructure/              # 共用基礎設施（不動）
│   │   ├── store.py                 # 新增 PM tables，保留 OHLCV
│   │   └── labeling.py             # 結算條件參數化
│   │
│   ├── polymarket/                  # ★ 新增
│   │   ├── __init__.py
│   │   ├── gamma_client.py
│   │   ├── clob_client.py
│   │   ├── market_tracker.py
│   │   ├── order_manager.py
│   │   └── pipeline.py             # Polymarket live 主控
│   │
│   ├── binance/                     # ★ 新增：從散落位置收攏
│   │   ├── __init__.py
│   │   ├── feed.py                  # ← WebSocket OHLCV（共用特徵源）
│   │   ├── settler.py               # ← Binance EC 結算邏輯
│   │   └── pipeline.py              # ← Binance EC live 主控
│   │
│   ├── strategies/                  # 共用框架（不動）
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── pm_v1/                   # ★ 新增（多 timeframe 共用）
│   │   ├── catboost_v1/            # 保留
│   │   ├── lgbm_v2/                # 保留
│   │   ├── xgboost_v1/             # 保留
│   │   ├── xgboost_v2/             # 保留
│   │   ├── lgbm_v1/                # 保留
│   │   └── mlp_v1/                 # 保留
│   │
│   ├── backtest/                    # 共用（結算條件參數化）
│   │   ├── engine.py
│   │   └── stats.py
│   │
│   ├── simulation/
│   │   └── risk.py                  # 支援 PM 風控
│   │
│   ├── discord_bot/
│   │   └── bot.py                   # Polymarket 整合
│   │
│   └── utils/
│       └── config.py
│
├── scripts/
│   ├── polymarket/                  # PM 調查腳本 + 新增運行腳本
│   │   └── ...
│   ├── binance/                     # ★ Binance 腳本收攏
│   │   ├── run_live_binance.py      # ← scripts/run_live.py
│   │   ├── fetch_history.py         # ← scripts/fetch_history.py
│   │   ├── run_live_supervised.sh   # ← scripts/run_live_supervised.sh
│   │   └── train_xgboost_model.py   # ← deprecated 腳本
│   ├── run_live.py                  # ★ 重寫為 PM 入口
│   ├── train_model.py               # 支援 PM 策略
│   ├── backtest.py                  # 支援 PM 結算
│   └── analyze_calibration.py
│
├── reports/
│   ├── polymarket/                  # 不動
│   └── binance/                     # ★ Binance 報告收攏
│       └── *.json
│
├── models/
│   ├── pm_v1/                       # 新（含 5m.pkl, 15m.pkl, ...）
│   ├── catboost_v1/                 # 保留
│   ├── lgbm_v2/                     # 保留
│   └── ...
│
├── data/
│   ├── btc_predictor.db
│   └── polymarket/
│       └── orderbook_snapshots.jsonl
│
└── tests/
    ├── test_polymarket/             # ★ 新增
    ├── test_binance/                # ★ Binance 測試收攏
    ├── test_strategies/             # 共用
    └── [共用測試保留原位]
```

### 3.3 收攏操作：具體移動清單

#### `src/btc_predictor/binance/` — 從 infrastructure/simulation 抽離

| 來源 | 目的地 | 操作 |
|------|--------|------|
| `infrastructure/pipeline.py` 的 WebSocket 邏輯 | `binance/feed.py` | **抽離**（不是搬移——feed 是共用特徵源） |
| `infrastructure/pipeline.py` 的 Binance EC 主控邏輯 | `binance/pipeline.py` | **抽離** |
| `simulation/settler.py` 的 Binance EC 結算邏輯 | `binance/settler.py` | **抽離** |

> ⚠️ **Pipeline 拆分是最高風險項**
>
> 目前 `infrastructure/pipeline.py` 同時負責 WebSocket 連接、OHLCV 組裝、策略觸發、模擬交易執行。拆分時要注意：
> - Binance WebSocket feed 是**共用元件**（PM 也需要 OHLCV 特徵），不能完全藏進 `binance/`
> - 建議 `binance/feed.py` 對外暴露 `BinanceFeed` class，供 `polymarket/pipeline.py` import
> - Signal Layer 寫入邏輯需在兩個 pipeline 都能觸發
>
> **建議 Phase 2 的第一個 task 專門處理 pipeline 拆分，不加新功能，純重構 + 測試。**

#### `scripts/binance/` — 從 scripts 根目錄收攏

| 來源 | 目的地 |
|------|--------|
| `scripts/run_live.py` | `scripts/binance/run_live_binance.py` |
| `scripts/fetch_history.py` | `scripts/binance/fetch_history.py` |
| `scripts/run_live_supervised.sh` | `scripts/binance/run_live_supervised.sh` |
| `scripts/train_xgboost_model.py` | `scripts/binance/train_xgboost_model.py` |

#### `reports/binance/` + `docs/binance/` + `tests/test_binance/`

| 類型 | 來源 | 目的地 |
|------|------|--------|
| 報告 | `reports/*.json` | `reports/binance/*.json` |
| 文件 | `docs/polymarket-patch.md` | `docs/binance/polymarket-patch.md` |
| 文件 | ARCHITECTURE.md Binance 段落 | `docs/binance/ARCHITECTURE-binance.md` |
| 測試 | `test_pipeline_trigger.py`, `test_live_integration.py`, `test_settler.py` | `tests/test_binance/` |

---

## 4. 遷移執行計畫

### Phase 1：文件遷移 + 結構重組（Task G3.0，不動 runtime logic）

**G3.0.1 — 核心文件遷移**
- DECISIONS.md / ARCHITECTURE.md / PROGRESS.md / constants / AGENTS.md

**G3.0.2 — 目錄結構重組**
- 建立 `src/btc_predictor/{polymarket,binance}/` 目錄
- 移動 scripts/reports/docs/tests
- 更新 import 路徑
- `uv run pytest` 全數通過

### Phase 2：Polymarket 基礎設施（Task G3.1）

- Pipeline 拆分（最高優先）
- `polymarket/gamma_client.py` + `clob_client.py`
- `polymarket/market_tracker.py`
- `labeling.py` 參數化
- SQLite migration

### Phase 3：多 timeframe 模型訓練 + 回測（Task G3.2）

- `strategies/pm_v1/`：CatBoost 基礎，>= 結算，5m/15m/1h/4h/1d 全跑
- Walk-forward 回測 × 每個 timeframe（PM fee 模型）
- Alpha 分析，找出最佳 timeframe-model 組合

### Phase 4：模擬交易驗證（Task G3.3）

- Paper trading + Discord Bot + 200 筆驗證

### Phase 5：Live Trading（Gate 4）

- VPS + wallet + CLOB trading + order management

---

## 5. 共用 vs 專用元件對照表

| 元件 | 分類 | 位置 |
|------|------|------|
| Binance WebSocket 1m OHLCV | **共用** | `binance/feed.py`（被 PM pipeline import） |
| Binance REST klines API | **共用** | `scripts/binance/fetch_history.py` |
| BaseStrategy / Registry | **共用** | `strategies/base.py`, `registry.py` |
| Signal Layer | **共用** | `infrastructure/store.py` |
| `ohlcv` 表 | **共用** | `infrastructure/store.py` |
| `prediction_signals` 表 | **共用** | `infrastructure/store.py` |
| `simulated_trades` 表 | **共用** | `infrastructure/store.py` |
| Backtest engine | **共用** | `backtest/engine.py`（結算條件參數化） |
| Discord Bot | **共用** | `discord_bot/bot.py`（適配 PM） |
| Binance EC 結算邏輯 | **Binance 專用** | `binance/settler.py` |
| Binance EC 模擬交易觸發 | **Binance 專用** | `binance/pipeline.py` |
| Polymarket CLOB client | **PM 專用** | `polymarket/clob_client.py` |
| Polymarket market tracker | **PM 專用** | `polymarket/market_tracker.py` |
| Polymarket order manager | **PM 專用** | `polymarket/order_manager.py` |

---

## 6. 風險與注意事項

### 6.1 Pipeline 拆分風險（最高優先處理）

目前 `infrastructure/pipeline.py` 是 ~300 行 monolith，拆分風險：
- WebSocket reconnect 邏輯（指數退避、heartbeat）搬動不當 → 連線不穩
- OHLCV buffer 共享狀態 → ownership 和 thread safety
- Signal Layer 寫入需在兩個 pipeline 都能觸發

**對策**：Phase 2 第一個 task 專門做 pipeline 拆分，純重構 + 測試，不加功能。

### 6.2 其他風險

| 風險 | 對策 |
|------|------|
| 結算條件差異 | `labeling.py` 必須參數化，不硬編碼 |
| VPS 地理限制 | GCP Tokyo 已驗證，需 fallback 方案 |
| Polygon 私鑰管理 | 環境變數 + secret manager |
| 台灣法規風險 | 限制 position size，避免政治類市場 |

### 6.3 明確不做的事

- **不重命名 package**
- **不刪除任何 Binance 程式碼**（收攏保留）
- **不同時維護兩個 live pipeline**（Binance live 暫停，僅保留 feed）
- **不在 Phase 1 動 runtime logic**

---

## 附錄：PM 調查完整結論索引

| 調查 | 狀態 | 關鍵結論 | 報告位置 |
|------|------|---------|---------|
| PM-0.1 | ✅ | 台灣 IP 可讀 API | `reports/polymarket/PM-0.1-api-access-test.md` |
| PM-0.2 | ✅ | GCP Tokyo 暢通，London 被封 | `reports/polymarket/PM-0.2-vps-relay-test.md` |
| PM-0.3 | ✅ | 法規風險中等，避免政治類 | `reports/polymarket/PM-0.3-legal-risk-assessment.md` |
| PM-0.4 | ✅ | E2E ~700-900ms，可操作 | `reports/polymarket/PM-0.4-architecture-latency.md` |
| PM-1 | ✅ | 5m lifecycle 清楚，`>=` 結算 | `reports/polymarket/PM-1-market-structure.md` |
| PM-2.1 | ✅ | Chainlink Data Streams 亞秒級 | `reports/polymarket/PM-2.1-chainlink-specs.md` |
| PM-4 | ✅ | Maker 免費，Taker ~3.12% | `reports/polymarket/PM-4-fee-structure.md` |
| PM-5 | ✅ | 🔴 市場高度校準，Brier 0.2489 | `reports/polymarket/PM-5-calibration-analysis.md` |
| PM-3-lite | ✅ | Spread 穩定 $0.01 | `reports/polymarket/PM-3-lite-spread-snapshot.md` |
| PM-6 | ✅ | 🟡 需 5m 專屬模型，alpha>5% 有 edge | `reports/polymarket/PM-6-model-alpha-baseline.md` |