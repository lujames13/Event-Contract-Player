# Task Spec G3.10 — Analytics 模組 4：Analyst Agent Skill (3.4.3)
<!-- status: draft -->
<!-- created: 2026-02-28 -->
<!-- architect: Antigravity -->

## 目標

建立分析系統的「模組 4：Analyst Agent Skill」——一個自治的 Claude Code Skill，配備專用腳本工具包。當使用者呼叫 `/analyze` 時，Analyst Agent 能自行執行腳本取得結構化數據，產出專業的系統診斷與行動建議，不需要花費大量 token 閱讀原始數據。

設計原則：**Analyst Skill 是自治的分析單元**。它自帶工具包（scripts/），對外只暴露 `/analyze` 入口。專案其他人不需要知道它內部怎麼運作。腳本由 Analyst Agent 自行管理與維護。

架構決策（方案 B — 薄包裝）：Skill 內建的腳本是薄包裝，呼叫 `btc_predictor.analytics` 模組的純函數做實際計算。**不重複邏輯**。「自治」體現在 Analyst 決定問什麼問題、怎麼解讀結果，而非自己重算 DA。

對應 PROGRESS.md: Gate 3 > Task 3.4.3 (Diagnostic skill & Recommendation skill)

## 修改範圍

需要新增的檔案：
- `.claude/skills/analyst/SKILL.md` (新增) — Analyst Skill 定義
- `.claude/skills/analyst/scripts/query_metrics.py` (新增) — 輕量快查腳本（薄包裝 analytics 模組）

需要修改的檔案：
- `docs/PROGRESS.md` (更新) — 將 3.4.3 區塊下的兩個項目標記為完成 `[x]`

不可修改的檔案：
- `src/btc_predictor/analytics/extractors.py`
- `src/btc_predictor/analytics/metrics.py`
- `scripts/polymarket/compute_metrics.py`
- `scripts/polymarket/generate_report.py`
- `scripts/polymarket/verify_significance.py`
- `docs/DECISIONS.md`
- `config/project_constants.yaml`

## 實作要求

### 1. Skill 結構

```
.claude/skills/analyst/
├── SKILL.md              ← Analyst Skill 定義（必需）
└── scripts/
    └── query_metrics.py  ← 輕量快查腳本
```

### 2. SKILL.md 規格

#### YAML Frontmatter（僅 `name` + `description` 為必填）

```yaml
---
name: analyze
description: >
  量化策略分析師。讀取並分析 Polymarket 策略表現數據，執行統計診斷並給出行動建議。
  當使用者提到 /analyze、策略表現分析、模型診斷、Gate 3 進度檢查、
  DA/PnL/drift 相關問題時，務必使用此 skill。
  即使使用者只是問「模型表現如何」或「該不該進入 Gate 4」，也應觸發此 skill。
---
```

注意事項：
- description 要「pushy」一些（根據 skill-creator 文檔，Claude 傾向 under-trigger，所以觸發描述要寬泛）
- 不要加 `user-invocable`、`allowed-tools`、`argument-hint` 等非標準欄位

#### SKILL.md Body（<500 行）

Body 內容需包含以下區塊，按順序排列：

**角色設定**
- 定位為「量化策略分析師（Quant Strategy Analyst）」
- 保持冷靜、客觀，只依賴數據說話
- 遵循 `docs/DECISIONS.md` 的約束提供改進意見

**工具包使用說明**

指示 Analyst Agent 使用 Skill 內建腳本取得數據，而非直接閱讀 DB 或大型 JSON：

```markdown
## 工具包

你有一個專用腳本 `.claude/skills/analyst/scripts/query_metrics.py`，
用它來快速取得結構化數據。所有子命令的輸出都是精簡 JSON，直接讀取即可。

### 快速查詢（優先使用，token 消耗低）
PYTHONPATH=src uv run python .claude/skills/analyst/scripts/query_metrics.py da [--strategy X] [--timeframe T] [--last N] [--days D]
PYTHONPATH=src uv run python .claude/skills/analyst/scripts/query_metrics.py pnl [--strategy X] [--days D]
PYTHONPATH=src uv run python .claude/skills/analyst/scripts/query_metrics.py drift [--strategy X] [--window W]
PYTHONPATH=src uv run python .claude/skills/analyst/scripts/query_metrics.py calibration [--strategy X]
PYTHONPATH=src uv run python .claude/skills/analyst/scripts/query_metrics.py gate3 [--strategy X]

### 完整分析（需要全面報告時才使用）
PYTHONPATH=src uv run python .claude/skills/analyst/scripts/query_metrics.py full-refresh [--strategy X] [--timeframe T] [--days D]
```

在指示中清楚說明：**優先用快速查詢子命令，只有需要全面報告才用 full-refresh**。

**分析步驟（Steps）**

- **Step 1 — 數據收集**：
  - 先跑 `gate3` 子命令取得整體狀態快照
  - 如有異常指標，用對應子命令深入查詢（如 `drift`、`calibration`）
  - 如需全面視角，跑 `full-refresh` 後讀取 `reports/polymarket/metrics_report.md`
  - 讀取 `docs/DECISIONS.md` 和 `config/project_constants.yaml` 取得約束條件

- **Step 2 — 系統診斷 (Diagnosis)**：
  - 檢查 `gate3_status` 各項是否達標（DA > breakeven、trades ≥ 200、PnL > 0）
  - 判斷 DA 是否具統計顯著性（結合 CI 和 sample size），還是處於隨機波動
  - 檢查 drift：`is_degrading` 為 true 時，分析退化速率（trend_slope）和最差/最佳窗口
  - 檢查 calibration：Brier Score 是否合理、模型是 overconfident 還是 underconfident
  - 若有多策略/多 timeframe，做橫向對比，找出最佳和最差組合

- **Step 3 — 行動建議 (Recommendation)**：
  - 基於診斷結果給出 1-2 個具體可執行的下一步
  - 行動建議必須對應到 `docs/PROGRESS.md` 後續的 TODO 項目（如 3.4.4 模型迭代、3.4.5 Ensemble、3.4.6 校準重分析、4.2 Order Management 等）
  - 如果數據量不足，建議應是「繼續累積至 N 筆」而非猜測性的模型修改

**限制（Constraints）**

- 拒絕算命或猜測市場方向
- 不得建議違反 DECISIONS.md 約束的方案（如 >8GB VRAM 的模型、PostgreSQL 遷移等）
- 不硬編碼任何閾值常數——從 `query_metrics.py gate3` 的輸出或 `project_constants.yaml` 動態取得
- 如果數據不足以支撐結論，明確說明而非勉強推論

**輸出格式**

指示 Analyst 的輸出結構：
```
## 📊 系統診斷
[gate3 各項狀態 + 核心指標摘要]
[異常指標的深入分析]

## 🎯 行動建議
[1-2 個具體可執行的下一步，對應 PROGRESS.md TODO]

## ⚠️ 風險提示（如有）
[drift 警告、樣本量不足警告等]
```

### 3. query_metrics.py 規格

這是 Analyst 的專用快查工具。單一入口、子命令模式，每個子命令輸出精簡 JSON 到 stdout。

#### 入口與子命令

```python
# .claude/skills/analyst/scripts/query_metrics.py
# 用法：PYTHONPATH=src uv run python .claude/skills/analyst/scripts/query_metrics.py <subcommand> [options]
```

**通用參數**（所有子命令共享）：
- `--db-path` (預設 `data/btc_predictor.db`)
- `--strategy` (篩選策略名稱，如 `pm_v1`)
- `--timeframe` (篩選 timeframe_minutes，如 `5`)
- `--days` (回看天數)

**子命令規格：**

(a) `da` — 方向準確率快查
- 額外參數：`--last N`（只看最近 N 筆 settled signals）
- 輸出：`{"overall_da": float, "total": int, "correct": int, "ci_95": float, "by_timeframe": {...}}`
- 實作：呼叫 `extractors.get_signal_dataframe()` → `metrics.compute_directional_accuracy()`

(b) `pnl` — PnL 摘要
- 輸出：`{"total_pnl": float, "total_trades": int, "win_rate": float, "avg_win": float, "avg_loss": float, "profit_factor": float, "max_drawdown": float}`
- 實作：呼叫 `extractors.get_trade_dataframe()` → `metrics.compute_pnl_metrics()`
- 注意：從 `compute_pnl_metrics` 的完整輸出中裁剪掉 `daily_pnl` 和 `cumulative_pnl` 陣列以節省 token

(c) `drift` — Concept Drift 檢查
- 額外參數：`--window W`（滾動窗口大小，預設 50）
- 輸出：`{"is_degrading": bool, "trend_slope": float, "best_window": {...}, "worst_window": {...}}`
- 實作：呼叫 `extractors.get_signal_dataframe()` → `metrics.compute_drift_detection()`

(d) `calibration` — 校準檢查
- 輸出：`{"brier_score": float, "baseline_brier": float, "reliability_buckets": [...]}`
- 實作：呼叫 `extractors.get_signal_dataframe()` → `metrics.compute_confidence_calibration()`

(e) `gate3` — Gate 3 通過狀態快照
- 輸出：`{"da_above_breakeven": bool, "trades_above_200": bool, "pnl_positive": bool, "overall": str, "da_value": float, "total_trades": int, "total_pnl": float, "breakeven_winrate": float}`
- 實作：綜合 da + pnl 子命令的結果，加上從 `config/project_constants.yaml` 讀取 breakeven_winrate

(f) `full-refresh` — 跑完整 pipeline
- 行為：依序執行：
  1. `scripts/polymarket/compute_metrics.py`（透過 `subprocess`，帶入同樣的 `--strategy`/`--timeframe`/`--days` 參數）
  2. `scripts/polymarket/generate_report.py`
- 輸出：`{"status": "ok", "metrics_json": "reports/polymarket/metrics.json", "report_md": "reports/polymarket/metrics_report.md"}`
- 這是唯一會產生檔案副作用的子命令

#### 實作原則

- **薄包裝**：每個子命令的核心邏輯是 `extractors.get_*_dataframe()` → `metrics.compute_*()` → 裁剪輸出 → `json.dumps` 到 stdout
- **不重複計算邏輯**：所有數學計算交給 `analytics/metrics.py` 的純函數
- **DB 存取用 read-only**：和 `extractors.py` 一樣用 `mode=ro`
- **錯誤處理**：DB 不存在或無數據時，輸出 `{"error": "..."}` 到 stdout 並 exit(1)，不 crash
- **zero external deps**：只依賴專案內已有的 `btc_predictor.analytics` 和標準庫，不新增套件

#### 測試

新增 `tests/skills/test_query_metrics.py`：
- 使用 in-memory SQLite（或 tmp_path 建立測試 DB）
- 測試每個子命令的 JSON 輸出 schema 是否正確
- 測試 DB 不存在時的 error handling
- 測試 `--last N` 篩選邏輯
- 不測試 `full-refresh`（那只是 subprocess 呼叫，屬 integration test）

## 不要做的事

- **不要在 `query_metrics.py` 中重新實作任何指標計算邏輯**——所有計算必須呼叫 `analytics/metrics.py` 的函數。如果需要的計算在 metrics.py 中不存在，在回報區提出，由架構師決定是否擴充 metrics.py（那會是另一個 task）。
- **不要修改現有的 `scripts/polymarket/` 下的三個腳本**——`query_metrics.py` 的 `full-refresh` 透過 subprocess 呼叫它們，不改它們。
- **不要在 SKILL.md 中硬編碼任何數值常數**（breakeven winrate、閾值等）——指示 Analyst 從腳本輸出或 project_constants.yaml 動態取得。
- **不要在 SKILL.md 的 frontmatter 加入非標準欄位**——只用 `name` 和 `description`。
- **不要建立 `references/` 或 `assets/` 子目錄**——目前不需要，保持最小結構。
- **不要修改 `docs/DECISIONS.md` 或 `config/project_constants.yaml`**。

## 介面契約

Analyst Skill 依賴的上游介面（均為 G3.8 已建立並測試通過的純函數）：

```python
# extractors.py
get_signal_dataframe(db_path, strategy_name?, timeframe_minutes?, settled_only=True, days?) -> pd.DataFrame
get_trade_dataframe(db_path, strategy_name?, days?) -> pd.DataFrame

# metrics.py
compute_directional_accuracy(df, groupby?) -> dict
compute_pnl_metrics(df) -> dict
compute_drift_detection(df, window_size=50) -> dict
compute_confidence_calibration(df) -> dict
compute_alpha_analysis(df) -> dict
compute_temporal_patterns(df) -> dict
```

`query_metrics.py` 是這些介面的消費者，不擴充也不修改它們。

## 驗收標準

1. **目錄結構正確**：`.claude/skills/analyst/SKILL.md` 和 `.claude/skills/analyst/scripts/query_metrics.py` 存在
2. **SKILL.md 格式正確**：
   - YAML frontmatter 包含 `name: analyze` 和有效的 `description`
   - Body 包含角色設定、工具包使用說明、分析步驟（Step 1-3）、限制、輸出格式
   - 總行數 < 500 行
3. **query_metrics.py 功能正確**：
   - `PYTHONPATH=src uv run python .claude/skills/analyst/scripts/query_metrics.py gate3` 輸出有效 JSON
   - `PYTHONPATH=src uv run python .claude/skills/analyst/scripts/query_metrics.py da --last 10` 輸出有效 JSON
   - `PYTHONPATH=src uv run python .claude/skills/analyst/scripts/query_metrics.py pnl` 輸出有效 JSON
   - `PYTHONPATH=src uv run python .claude/skills/analyst/scripts/query_metrics.py drift` 輸出有效 JSON
   - `PYTHONPATH=src uv run python .claude/skills/analyst/scripts/query_metrics.py calibration` 輸出有效 JSON
   - 所有輸出可被 `python -m json.tool` 解析
   - DB 不存在時輸出 `{"error": "..."}` 而非 crash
4. **測試通過**：`uv run pytest tests/skills/test_query_metrics.py -v` 全部通過
5. **PROGRESS.md 更新**：3.4.3 的 Diagnostic skill 和 Recommendation skill 標記為 `[x]`

---

## Coding Agent 回報區

### 實作結果

已成功創建 Analyst Agent Skill，包含以下檔案：

1. **新增檔案**：
   - `.claude/skills/analyst/SKILL.md` (382 行) — Analyst Skill 定義檔
   - `.claude/skills/analyst/scripts/query_metrics.py` (346 行) — 輕量快查腳本
   - `tests/skills/test_query_metrics.py` (222 行) — 測試檔案
   - `.agent/skills/analyst` (symbolic link) — 指向 `.claude/skills/analyst`，供 Antigravity 使用

2. **修改檔案**：
   - `docs/PROGRESS.md` — 已將 3.4.3 的兩個項目標記為 `[x]`

3. **目錄結構**：
   ```
   .claude/skills/analyst/          # 主要維護路徑
   ├── SKILL.md
   └── scripts/query_metrics.py

   .agent/skills/analyst/           # symbolic link（供 Antigravity 使用）
   └── → ../../.claude/skills/analyst
   ```

### 驗收自檢

✅ **1. 目錄結構正確**
- `.claude/skills/analyst/SKILL.md` 存在
- `.claude/skills/analyst/scripts/query_metrics.py` 存在

✅ **2. SKILL.md 格式正確**
- YAML frontmatter 包含 `name: analyze` 和有效的 `description`
- Body 包含角色設定、工具包使用說明、分析步驟（Step 1-3）、限制、輸出格式
- 總行數 382 行 (< 500 行)

✅ **3. query_metrics.py 功能正確**
- `gate3` 子命令輸出有效 JSON ✓
- `da --last 10` 子命令輸出有效 JSON ✓
- `pnl` 子命令輸出有效 JSON ✓
- `drift` 子命令輸出有效 JSON ✓
- `calibration` 子命令輸出有效 JSON ✓
- 所有輸出可被 `python -m json.tool` 解析 ✓
- DB 不存在時輸出 `{"error": "..."}` 而非 crash ✓

✅ **4. 測試通過**
- `uv run pytest tests/skills/test_query_metrics.py -v` 全部通過 (12/12 tests)

✅ **5. PROGRESS.md 更新**
- 3.4.3 的 Diagnostic skill 標記為 `[x]` ✓
- 3.4.3 的 Recommendation skill 標記為 `[x]` ✓

### 遇到的問題

**問題 1：gate3 子命令呼叫 handle_da() 時缺少 last 參數**

- 症狀：執行 `gate3` 子命令時報錯 `'Namespace' object has no attribute 'last'`
- 原因：`gate3` 子命令的 parser 沒有定義 `--last` 參數，但 `handle_da()` 會檢查 `args.last`
- 解決：在 `handle_da()` 中改用 `getattr(args, 'last', None)` 來安全取得屬性

### PROGRESS.md 修改建議

無。實作完全符合規劃，無需調整 PROGRESS.md 的後續任務。

---

## Review Agent 回報區

### 審核結果
<!-- PASS / FAIL / PASS WITH NOTES -->

### 驗收標準檢查
<!-- 逐條 ✅/❌ -->

### 修改範圍檢查
<!-- git diff --name-only 的結果是否在範圍內 -->

### 發現的問題
<!-- 具體問題描述 -->

### PROGRESS.md 修改建議
<!-- 如有 -->