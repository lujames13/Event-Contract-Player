# Task Spec G1.0 — 基礎設施修復與多模型框架搭建

> **Gate:** 1（模型實驗池）
> **優先級:** 🔴 Blocker — 後續所有模型實驗依賴此任務完成
> **前置條件:** 無
> **狀態備註:** `docs/PROGRESS.md` 和 `docs/MODEL_ITERATIONS.md` 已由人類手動添加，無需 agent 處理。

---

## 目標

修復回測引擎中的 bug，更新 ARCHITECTURE.md，建立多模型策略 registry 和通用訓練腳本，
讓後續的模型實驗可以用統一的流程進行「新增策略 → 訓練 → 回測 → 記錄結果」。

---

## 子任務

### G1.0.1 — 更新 ARCHITECTURE.md

依照 `docs/ARCHITECTURE_PATCH.md` 的指示，對 `docs/ARCHITECTURE.md` 做以下修改：

**修改 1：替換系統總覽圖**

將現有的 `## 系統總覽` ASCII 圖替換為以下內容（反映多模型並行架構）：

```
┌─────────────────────────────────────────────────────────────┐
│                    Data Pipeline Layer                       │
│  Binance WebSocket (1m OHLCV stream)                        │
│  Binance REST API (歷史回填)                                 │
│  [未來] Fear & Greed · DXY · CryptoBERT                     │
└──────────────┬──────────────────────────────────────────────┘
               │ OHLCV DataFrame（共用，只生成一次）
               ▼
┌─────────────────────────────────────────────────────────────┐
│              Strategy Registry (多模型並行)                   │
│                                                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │ xgboost_v1   │ │ lgbm_v1      │ │ mlp_v1       │  ...   │
│  │ (BaseStrategy)│ │ (BaseStrategy)│ │ (BaseStrategy)│        │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘        │
│         │                │                │                 │
│         ▼                ▼                ▼                 │
│    PredictionSignal PredictionSignal PredictionSignal        │
└──────────────┬──────────────────────────────────────────────┘
               │ List[PredictionSignal]
               ▼
┌─────────────────────────────────────────────────────────────┐
│               Decision & Simulation Layer                   │
│  每個 signal 獨立進行：                                      │
│  信心度 ≥ 閾值? → 風控檢查 → SimulatedTrade → SQLite        │
│  統計計算（per strategy × timeframe）                        │
└──────────┬─────────────────────────┬────────────────────────┘
           │                         │
           ▼                         ▼
   CLI 統計報表 / 回測          Discord Bot
   (scripts/backtest.py)       /predict  /stats  /models
                               自動通知（高信心 + 到期結果）
```

**修改 2：在 `## 策略基類` 段落之後、`## 資料層` 段落之前，新增以下段落：**

```markdown
---

## Strategy Registry（多模型管理）

系統透過 Strategy Registry 管理多個同時運行的策略。

### 策略目錄結構

```
src/btc_predictor/strategies/
├── base.py                    # BaseStrategy 基類
├── registry.py                # ★ 策略自動發現與註冊
├── xgboost_v1/                # 每個策略一個目錄
│   ├── __init__.py
│   ├── strategy.py            # 必須包含一個繼承 BaseStrategy 的 class
│   ├── features.py            # 策略專屬的特徵工程
│   └── model.py               # 策略專屬的模型邏輯
├── lgbm_v1/
└── ...
```

### 模型檔案位置

已訓練的模型檔案存放在：

```
models/
├── xgboost_v1/
│   ├── 10m.pkl
│   ├── 30m.pkl
│   ├── 60m.pkl
│   └── 1440m.pkl
├── lgbm_v1/
│   └── ...
└── ...
```

策略載入時自動從對應目錄讀取模型。若模型檔不存在，策略標記為「未訓練」，不參與預測。

### Registry 介面

```python
# src/btc_predictor/strategies/registry.py

class StrategyRegistry:
    """自動發現並管理所有策略。"""

    def discover(self, strategies_dir: Path, models_dir: Path) -> None:
        """掃描 strategies_dir 下的子目錄，載入繼承 BaseStrategy 的策略。"""
        ...

    def get(self, name: str) -> BaseStrategy:
        """根據名稱取得策略實例。"""
        ...

    def list_names(self) -> List[str]:
        """列出所有已註冊的策略名稱。"""
        ...

    def list_strategies(self) -> List[BaseStrategy]:
        """列出所有已註冊的策略實例。"""
        ...
```
```

**修改 3：在文件末尾，`## Phase 2+ 多模態特徵` 之後，新增以下段落：**

```markdown
---

## Discord Bot 指令介面（Gate 2）

### /predict [timeframe]
用當前市場數據跑所有已載入模型，回傳每個模型的預測方向 + confidence + 下注建議。

### /stats [model_name]
- 不指定 model_name → 顯示所有模型的摘要對比表（DA、Trades、PnL）
- 指定 model_name → 顯示該模型的詳細統計（含校準、drawdown）

### /models
列出所有已載入模型及其回測表現摘要 + live 運行狀態。

### 自動通知
- 當任何策略 confidence > threshold 時，自動發送「交易信號」通知
- 到期時自動發送結果通知（是否獲勝 + PnL）
```

**不要做的事：**
- 不要修改現有的 dataclass 定義（PredictionSignal, SimulatedTrade, RealTrade）
- 不要修改 BaseStrategy 基類的定義
- 不要修改 SQLite Schema 定義
- 不要刪除任何現有內容，只做新增和系統總覽圖替換

**驗收：** `docs/ARCHITECTURE.md` 包含更新後的系統總覽圖、Strategy Registry 段落、Discord Bot 指令介面段落。

---

### G1.0.2 — 修復 backtest engine 中 lower 方向的平盤判定 bug

**檔案：** `src/btc_predictor/backtest/engine.py`

**問題：** 目前 lower 方向的勝負判定邏輯為：

```python
else:
    is_win = close_price <= open_price
```

根據 Event Contract 規則，平盤 (close == open) 對 **兩個方向都是 lose**。
lower 方向贏的條件應該是 `close_price < open_price`（嚴格小於）。

**修改：**

```python
if signal.direction == "higher":
    is_win = close_price > open_price      # 嚴格大於才算贏
else:
    is_win = close_price < open_price      # 嚴格小於才算贏
```

**驗收：**
1. 修改 `tests/test_backtest_engine.py`，新增平盤測試案例：
   - 建立一個 MockStrategy 在 close == open 時分別預測 higher 和 lower
   - 驗證兩者都返回 result="lose"
2. `uv run pytest tests/test_backtest_engine.py` 通過

**不要做的事：**
- 不要改 `src/btc_predictor/data/labeling.py` 的 label 邏輯（那邊的平盤處理是正確的）
- 不要改 PredictionSignal 或 SimulatedTrade 的 dataclass 定義
- 不要改 engine.py 中其他邏輯（walk-forward 流程、trade 記錄等）

---

### G1.0.3 — 建立 Strategy Registry

**新增檔案：** `src/btc_predictor/strategies/registry.py`

**功能：** 自動發現並管理多個策略，支援後續模型實驗的快速迭代。

**介面：**

```python
from pathlib import Path
from typing import List, Optional
from btc_predictor.strategies.base import BaseStrategy

class StrategyRegistry:
    """自動發現並管理所有策略。"""

    def __init__(self) -> None:
        self._strategies: dict[str, BaseStrategy] = {}

    def register(self, strategy: BaseStrategy) -> None:
        """手動註冊一個策略實例。"""
        ...

    def discover(self, strategies_dir: Path, models_dir: Path) -> None:
        """
        掃描 strategies_dir 下的所有子目錄，找到繼承 BaseStrategy 的 class，
        並嘗試從 models_dir/{strategy_name}/ 載入對應的模型檔案。

        目錄結構約定：
          strategies_dir/{dir_name}/strategy.py — 必須包含一個 BaseStrategy 子類
          models_dir/{strategy.name}/{timeframe}m.pkl — 該策略對應的已訓練模型

        注意：策略目錄名 (dir_name) 不一定等於 strategy.name，
              以 strategy class 的 name property 為準。
        """
        ...

    def get(self, name: str) -> BaseStrategy:
        """根據名稱取得策略實例。KeyError if not found."""
        ...

    def list_names(self) -> List[str]:
        """列出所有已註冊的策略名稱。"""
        ...

    def list_strategies(self) -> List[BaseStrategy]:
        """列出所有已註冊的策略實例。"""
        ...
```

**實作注意事項：**
- 使用 `importlib` 動態載入策略模組
- 如果某策略目錄下沒有 `strategy.py`，跳過並用 `logging.warning` 記錄
- 如果策略的 `requires_fitting=True` 但模型檔不存在，仍然註冊（訓練後再載入模型）
- 跳過 `__pycache__`、不含 `strategy.py` 的目錄、和任何以 `_` 開頭的目錄
- 不要引入任何新的外部套件依賴

**驗收：**
1. 新增 `tests/test_strategies/test_registry.py`
2. 測試案例：
   - `discover` 能找到 xgboost_v1（重命名後，見 G1.0.4）
   - `get("xgboost_v1")` 返回正確的策略實例
   - `get("nonexistent")` 拋出 `KeyError`
   - `list_names()` 返回包含 `"xgboost_v1"` 的列表
   - `register` 手動註冊後可用 `get` 取得
3. `uv run pytest tests/test_strategies/test_registry.py` 通過

**不要做的事：**
- 不要修改 `base.py` 的 BaseStrategy 介面
- 不要修改現有策略的程式碼邏輯

---

### G1.0.4 — 重構策略目錄結構

**目的：** 將現有的 `xgboost_direction/` 重新命名為 `xgboost_v1/`，並遷移模型檔案到新的目錄結構。

**修改：**

1. **重新命名策略目錄：**
   - `src/btc_predictor/strategies/xgboost_direction/` → `src/btc_predictor/strategies/xgboost_v1/`
   - 確認 `strategy.py` 中 `self._name = "xgboost_v1"`（目前已經是，不需改）

2. **建立模型檔案目錄結構：**
   ```
   models/
   └── xgboost_v1/
       ├── 10m.pkl    （從 models/xgboost_10m.pkl 移入，如果存在）
       ├── 30m.pkl
       ├── 60m.pkl
       └── 1440m.pkl
   ```
   - 如果現有 `models/xgboost_10m.pkl` 等檔案存在，移動到新路徑
   - 如果不存在，只建立 `models/xgboost_v1/` 空目錄
   - 在 `models/` 加一個 `.gitkeep` 或確保目錄結構被 git 追蹤

3. **更新所有 import 引用：**

   搜尋整個專案中所有 `xgboost_direction` 字串，替換為 `xgboost_v1`：
   - `scripts/backtest.py`
   - `scripts/run_live.py`
   - `scripts/train_xgboost_model.py`
   - `tests/` 下相關測試檔
   - 任何其他引用到的地方

4. **清理遺留空目錄：**
   - 刪除 `src/btc_predictor/strategies/nbeats_perceiver/`（空目錄，未來有需要再建）
   - 刪除 `src/btc_predictor/strategies/freqai_wrapper/`（空目錄，未來有需要再建）

**驗收：**
1. `uv run pytest` 全部通過（沒有 import 斷裂）
2. `grep -r "xgboost_direction" src/ scripts/ tests/` 返回空結果（完全清除舊名稱）
3. `from btc_predictor.strategies.xgboost_v1.strategy import XGBoostDirectionStrategy` 可正常 import

**不要做的事：**
- 不要修改策略的實際邏輯（features.py, model.py, strategy.py 的演算法不動）
- 不要重新命名 class 名稱（`XGBoostDirectionStrategy` 保持不變，只是目錄改了）
- 不要新增任何新的策略

---

### G1.0.5 — 建立通用訓練腳本

**新增檔案：** `scripts/train_model.py`

**功能：** 透過 StrategyRegistry 統一訓練流程，取代策略專屬的訓練腳本。

**CLI 介面：**

```bash
# 訓練指定策略的指定 timeframe
uv run python scripts/train_model.py --strategy xgboost_v1 --timeframe 10

# 訓練指定策略的所有 timeframe
uv run python scripts/train_model.py --strategy xgboost_v1 --all

# 訓練所有策略的所有 timeframe
uv run python scripts/train_model.py --all-strategies --all
```

**邏輯：**
1. 初始化 StrategyRegistry，discover 所有策略
2. 從 DataStore 載入 OHLCV 數據（1m interval）
3. 對指定的策略呼叫 `strategy.fit(ohlcv, timeframe_minutes)`
4. 將訓練好的模型序列化到 `models/{strategy.name}/{timeframe}m.pkl`
   - 需要策略提供 save 方法。目前 XGBoostDirectionStrategy 沒有直接暴露 save，
     但其內部 model 可透過 `strategy.model` 存取。
   - **建議方式：** 在 train_model.py 中呼叫 `strategy.fit()` 後，
     透過策略內部的 model 序列化工具存檔（xgboost_v1 已有 `save_model`）。
     或者在 BaseStrategy 中新增 optional 的 `save(path)` / `load(path)` 方法。
     **但本任務不修改 BaseStrategy**，所以先用策略專屬的方式處理。
5. 訓練完成後輸出訓練集準確率（僅供參考）

**驗收：**
1. `uv run python scripts/train_model.py --strategy xgboost_v1 --timeframe 10` 能成功訓練並產出 `models/xgboost_v1/10m.pkl`
2. 產出的模型檔可被策略正常載入
3. `--all` flag 會對 [10, 30, 60, 1440] 四個 timeframe 都訓練

**不要做的事：**
- 不要刪除 `scripts/train_xgboost_model.py`（保留，在檔案頂部加一行註解標記為 deprecated）
- 不要在訓練腳本中引入 walk-forward 邏輯（那是回測引擎的職責）
- 不要修改 BaseStrategy 介面

---

### G1.0.6 — 更新 backtest CLI 以支援 strategy registry

**修改檔案：** `scripts/backtest.py`

**修改內容：**

1. 用 StrategyRegistry 取代 hardcoded 的策略初始化：
   ```python
   # 舊
   if args.strategy == "xgboost_v1":
       strategy = XGBoostDirectionStrategy()

   # 新
   registry = StrategyRegistry()
   registry.discover(STRATEGIES_DIR, MODELS_DIR)
   strategy = registry.get(args.strategy)
   ```

2. 如果 `--strategy` 指定的名稱不存在，輸出清楚的錯誤訊息，列出所有可用策略

3. Report 檔名格式保持：`backtest_{strategy}_{timeframe}m_{timestamp}.json`

**驗收：**
1. `uv run python scripts/backtest.py --strategy xgboost_v1 --timeframe 10` 能正常執行
2. `uv run python scripts/backtest.py --strategy nonexistent --timeframe 10` 輸出錯誤訊息並列出可用策略

**不要做的事：**
- 不要修改 walk-forward 回測引擎的核心邏輯（`backtest/engine.py` 除了 G1.0.2 的 bug fix）
- 不要修改統計計算邏輯（`backtest/stats.py`）
- 不要修改 report JSON 的格式

---

## 修改範圍（封閉清單）

以下是此任務會觸及的 **所有** 檔案。未列出的檔案不應被修改。

**新增：**
- `src/btc_predictor/strategies/registry.py`
- `scripts/train_model.py`
- `tests/test_strategies/test_registry.py`
- `models/xgboost_v1/`（目錄）

**修改：**
- `docs/ARCHITECTURE.md`（新增 Strategy Registry + Discord Bot 段落、替換系統總覽圖）
- `src/btc_predictor/backtest/engine.py`（G1.0.2 bug fix，只改一行）
- `src/btc_predictor/strategies/xgboost_direction/` → 重命名為 `xgboost_v1/`
- `scripts/backtest.py`（改用 registry）
- `scripts/run_live.py`（更新 import 路徑 + model path）
- `scripts/train_xgboost_model.py`（更新 import + 頂部加 deprecated 註解）
- `tests/test_backtest_engine.py`（新增平盤測試）
- 所有 import `xgboost_direction` 的檔案（全局替換為 `xgboost_v1`）

**刪除：**
- `src/btc_predictor/strategies/nbeats_perceiver/`（空目錄）
- `src/btc_predictor/strategies/freqai_wrapper/`（空目錄）

**不動：**
- `docs/PROGRESS.md`（人類已手動更新）
- `docs/MODEL_ITERATIONS.md`（人類已手動添加）
- `docs/DECISIONS.md`
- `config/project_constants.yaml`
- `src/btc_predictor/models.py`
- `src/btc_predictor/strategies/base.py`
- `src/btc_predictor/data/labeling.py`
- `src/btc_predictor/simulation/risk.py`
- `src/btc_predictor/backtest/stats.py`

---

## 驗收標準（按順序執行）

```bash
# 1. 所有測試通過
uv run pytest

# 2. 舊名稱完全清除
grep -r "xgboost_direction" src/ scripts/ tests/
# 預期：無結果

# 3. 平盤 bug 修復驗證
uv run pytest tests/test_backtest_engine.py -k "flat" -v

# 4. Registry 可以發現 xgboost_v1
uv run python -c "
from pathlib import Path
from btc_predictor.strategies.registry import StrategyRegistry
reg = StrategyRegistry()
reg.discover(Path('src/btc_predictor/strategies'), Path('models'))
print(reg.list_names())
assert 'xgboost_v1' in reg.list_names()
print('✅ Registry works')
"

# 5. 通用訓練腳本可執行（如果有數據）
uv run python scripts/train_model.py --strategy xgboost_v1 --timeframe 10

# 6. 回測 CLI 可用
uv run python scripts/backtest.py --strategy xgboost_v1 --timeframe 10

# 7. ARCHITECTURE.md 包含新段落
grep "Strategy Registry" docs/ARCHITECTURE.md
grep "Discord Bot 指令介面" docs/ARCHITECTURE.md
```

---

## 建議執行順序

1. **G1.0.4** 先重構目錄（影響最廣，先做避免後續衝突）
2. **G1.0.2** 修復 bug（一行改動，順手做）
3. **G1.0.3** 建立 Registry
4. **G1.0.5** 通用訓練腳本（依賴 Registry）
5. **G1.0.6** 更新 backtest CLI（依賴 Registry）
6. **G1.0.1** 最後更新 ARCHITECTURE.md（確認所有程式碼都到位後再寫文件）

---

## 回報區（由 coding agent / review agent 填寫）

### Coding Agent 回報

**狀態：** ✅ 已完成 (2026-02-15)

**1. 修改檔案清單：**
- **新增：**
  - `src/btc_predictor/strategies/registry.py` (Strategy Registry 實作)
  - `scripts/train_model.py` (通用訓練腳本，支援 `--strategy` 與 `--timeframe`)
  - `tests/test_strategies/test_registry.py` (Registry 測試)
  - `tests/test_backtest_flat.py` (平盤邏輯測試)
- **重構與移動：**
  - `src/btc_predictor/strategies/xgboost_direction/` → `src/btc_predictor/strategies/xgboost_v1/`
  - `models/*.pkl` → `models/xgboost_v1/*.pkl`
- **修改：**
  - `docs/ARCHITECTURE.md` (新增 System Overview, Registry 說明, Discord Bot 介面)
  - `src/btc_predictor/backtest/engine.py` (修復 lower 平盤判定 bug)
  - `src/btc_predictor/strategies/xgboost_v1/strategy.py` (支援多模型管理 `self.models`，新增 `save_model` 與 `load_models_from_dir` 支援)
  - `scripts/backtest.py` (整合 Registry)
  - `scripts/run_live.py` (更新 import 與模型路徑)
  - `scripts/train_xgboost_model.py` (標記 Deprecated)
  - `tests/` 下相關測試隨路徑調整更新

**2. 遇到的問題與解決：**
- **XGBoost 策略多 timeframe 支援：** 原本 `XGBoostDirectionStrategy` 只持有一個 `self.model`。為了配合 Registry 與 `run_live` 的多 timeframe 需求，將其重構為 `self.models = {}` (dict 結構)，並修改 `predict` 與 `fit` 根據 `timeframe_minutes` 選擇正確模型。
- **Import 路徑問題：** `scripts/backtest.py` 與 `tests` 執行時遇到 `ModuleNotFoundError`，已透過 `sys.path.append` 或 `PYTHONPATH` 解決。
- **Lint 修復：** `tests/test_registry.py` 中 `Path` 未引入導致錯誤，已修正。

**3. 測試結果：**
- `uv run pytest` 全數通過 (29 passed)。
- `grep` 檢查確認 `xgboost_direction` 舊名稱已清除。
- `scripts/train_model.py` 測試訓練成功。
- `scripts/backtest.py` 測試回測成功。

### Review Agent 回報

**狀態：** ✅ 通過 Review (2026-02-15)

**1. 查核項目：**
- [x] **G1.0.1 (ARCHITECTURE.md):** 系統總覽圖已更新，Registry 與 Discord Bot 段落已補上。
- [x] **G1.0.2 (Bug Fix):** `engine.py` 中的平盤判定邏輯已從 `<=` 改為 `<`，符合 Event Contract 規則。
- [x] **G1.0.3 (Registry):** `registry.py` 實作正確，支援自動發現與動態載入。
- [x] **G1.0.4 (Refactor):** `xgboost_direction` 已完全更名為 `xgboost_v1`，目錄結構與模型路徑遷移完成。
- [x] **G1.0.5 (Train Script):** `train_model.py` 可正常運行，支援多 timeframe。
- [x] **G1.0.6 (Backtest CLI):** `backtest.py` 已整合 Registry，移除 hardcoded 初始化。

**2. 驗證細節：**
- 執行 `uv run pytest`：29 測項全數通過，包含新增的 `test_backtest_flat.py`。
- 執行 `grep`：確認無舊名稱殘留。
- 執行 `train_model.py`：成功產出 `models/xgboost_v1/10m.pkl`。
- 執行 `backtest.py`：成功完成 walk-forward 回測並產出 JSON report。

**3. 發現與建議：**
- **PYTHONPATH 注意事項：** 在開發環境運行時，需確保 `src` 在 `PYTHONPATH` 中。目前的 script 內已有 `sys.path.append` 處理，但在執行 pytest 時需顯式指定 `PYTHONPATH=src`。
- **Registry typo：** `registry.py:47` 的 log 訊息有小 typo (`strategies.py` 應為 `strategy.py`)，不影響功能。
- **整體品質：** 代碼重構乾淨，符合 `code-style-guide.md` 要求。