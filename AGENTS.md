# Agent Instructions

> 這份文件是 AI coding agent 的開工指南。每次對話開始前，先讀這份。

## 開工前必讀（按順序）

1. `docs/PROGRESS.md` — 了解當前狀態、下一步是什麼
2. `docs/DECISIONS.md` — 不可變的技術約束，不要違反
3. `docs/ARCHITECTURE.md` — 系統架構、介面契約、資料結構定義
4. `config/project_constants.yaml` — 所有硬性參數

## 核心規則

### 不可變文件
- **不要修改** `docs/DECISIONS.md`、`config/project_constants.yaml`
- 如果你認為某個決策需要更改，在 `docs/PROGRESS.md` 的 `Known Issues / Discussion` 區塊提出，等人類 review

### 介面契約
- 所有策略必須繼承 `strategies/base.py` 的 `BaseStrategy`
- 所有策略的輸出必須是 `PredictionSignal` dataclass（定義見 `docs/ARCHITECTURE.md`）
- 模擬倉交易記錄使用 `SimulatedTrade` dataclass
- 真實交易記錄使用 `RealTrade` dataclass

### 程式碼品質
- 每個模組都要有對應的 pytest 測試（放在 `tests/` 對應路徑下）
- type hints 必寫
- docstring 必寫（Google style）
- import 順序：stdlib → third-party → local

### 完成任務後
- **必須更新** `docs/PROGRESS.md`：
  - 將完成的 task 從 `In Progress` 移到 `Completed`，標注日期
  - 記錄關鍵產出（檔案路徑、測試結果、metrics）
  - 列出發現的 blockers 或 issues
- Commit message 格式：`[phase-X.Y] 簡述`
  - 例：`[phase-1.1] init project structure and constants`
  - 例：`[phase-1.2] implement XGBoost feature engineering`

## 套件管理

本專案使用 **uv** 管理 Python 環境與依賴。

```bash
# 安裝依賴（首次 clone 或 uv.lock 更新後）
uv sync

# 新增套件
uv add <package>

# 新增開發用套件
uv add --dev <package>

# 在 uv 管理的虛擬環境中執行指令
uv run <command>
```

### Agent 注意事項
- **不要使用** `pip install`，一律用 `uv add`
- 新增套件後，`pyproject.toml` 和 `uv.lock` 都會自動更新，兩者都要 commit
- ta-lib 有 C dependency，`pyproject.toml` 裡已宣告，但系統需預先安裝 TA-Lib C library

## 常用指令

```bash
# 測試
uv run pytest tests/

# 回測（Phase 1+）
uv run python scripts/backtest.py --strategy <strategy_name> --timeframe <10|30|60|1440>

# 即時運行（Phase 2+）
uv run python scripts/run_live.py

# 資料抓取
uv run python scripts/fetch_history.py --symbol BTCUSDT --intervals 1m,5m,1h,1d
```

## 專案結構速覽

```
project/
├── AGENTS.md                          ← 你在這裡
├── pyproject.toml                     # uv 專案定義 + 依賴
├── uv.lock                            # uv lock file（自動生成，需 commit）
├── .python-version                    # 鎖定 3.12
├── docs/
│   ├── ROADMAP.md                     # 高層規劃（參考用，不需更新）
│   ├── DECISIONS.md                   # 不可變技術決策
│   ├── ARCHITECTURE.md                # 系統架構 + 介面契約
│   └── PROGRESS.md                    # ★ Single Source of Truth
├── config/
│   └── project_constants.yaml         # 硬性參數
├── src/
│   └── btc_predictor/                 # 主套件（uv init 的 src layout）
│       ├── __init__.py
│       ├── data/
│       │   ├── pipeline.py            # Binance WebSocket + REST 數據抓取
│       │   └── store.py               # SQLite 讀寫
│       ├── strategies/
│       │   ├── base.py                # 策略基類
│       │   ├── nbeats_perceiver/
│       │   ├── xgboost_direction/
│       │   └── freqai_wrapper/
│       └── simulation/
│           ├── engine.py              # 模擬倉引擎
│           └── stats.py               # 統計計算
├── discord_bot/
│   └── bot.py                         # Phase 3
├── scripts/
│   ├── backtest.py                    # 歷史回測
│   ├── fetch_history.py               # 歷史數據抓取
│   └── run_live.py                    # 即時運行入口
└── tests/
    ├── test_data/
    ├── test_strategies/
    └── test_simulation/
```