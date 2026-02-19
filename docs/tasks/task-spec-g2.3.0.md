# Task Spec G2.3.0 — 系統成熟度提升：文件同步 + Flaky Test 修復 + 運維穩健性

<!-- status: review -->
<!-- created: 2026-02-19 -->
<!-- architect: Claude (Antigravity) -->

> **Gate:** 2（Live 系統）
> **優先級:** 🟡 Medium — 清除技術債，為長時間穩定運行掃除障礙
> **前置條件:** G2.2.1 完成（校準分析工具已上線）

---

## 目標

本 task 聚焦三個面向：

1. **文件同步**：將 G2.2.0 和 G2.2.1 的完成狀態正確反映在 `PROGRESS.md`，並將 `get_settled_signals` 方法補入 `ARCHITECTURE.md` 的介面契約。
2. **Flaky Test 修復**：`test_run_backtest_basic` 存在不穩定斷言（期望 1440 筆但平行化回測偶爾產出 1436-1439 筆），需根本性修復而非忽略。
3. **運維穩健性**：新增 `scripts/run_live_supervised.sh` wrapper 腳本，實現 crash-then-restart 機制（含日誌輪替），使系統可在背景穩定運行超過 24 小時，推動 Phase 1 穩定性軌道完成。

**解決的核心問題：**
- PROGRESS.md 中 2.4.1 / 2.4.2 仍標記為未完成，與實際不符
- 平行化回測引擎有 race condition 導致偶發測試失敗，影響 CI 信心
- live 系統目前依賴前台 `asyncio.run(main())`，一旦 crash 無人工介入就永久停機

---

## 子任務

### G2.3.0.0 — 文件同步：PROGRESS.md 更新

**檔案：** `docs/PROGRESS.md`

**修改：**

1. 將 `2.4.1 Signal Layer 實作 (G2.2.0)` 的 `[ ]` 改為 `[x]`
2. 將 `2.4.2 校準分析工具 (G2.2.1)` 的 `[ ]` 改為 `[x]`
3. 在 2.4.2 下方加上完成日期註釋：`Completed: 2026-02-19`

**驗收：**
```bash
grep "\[x\].*2.4.1" docs/PROGRESS.md
grep "\[x\].*2.4.2" docs/PROGRESS.md
```

---

### G2.3.0.1 — 文件同步：ARCHITECTURE.md 補充 get_settled_signals

**檔案：** `docs/ARCHITECTURE.md`

在 DataStore 介面契約段落（`get_signal_stats` 方法之後），新增：

```python
def get_settled_signals(
    self,
    strategy_name: str | None = None,
    timeframe_minutes: int | None = None
) -> pd.DataFrame:
    """取得已結算的 prediction signals，供校準分析使用。"""
```

**驗收：**
```bash
grep "get_settled_signals" docs/ARCHITECTURE.md
```

---

### G2.3.0.2 — Flaky Test 修復：test_run_backtest_basic

**檔案：** `tests/test_backtest_engine.py`

**現象：** 平行化 walk-forward 回測引擎在某些情況下產出交易筆數略少於理論值（1436-1439 vs 期望 1440），導致 `assert len(trades) == 1440` 不穩定失敗。

**根因分析方向：**
1. 檢查 `backtest/engine.py` 的平行化邏輯，確認 fold 邊界是否有 off-by-one 導致部分 K 線被遺漏
2. 檢查 walk-forward 的 `train_days` / `test_days` 切分是否在跨日邊界處遺失了幾筆資料
3. 檢查平行化時的資料共用是否有 race condition

**修復策略（按優先度）：**

a. **如果是 fold 邊界 off-by-one**：修正 `engine.py` 的切分邏輯，使每筆 K 線精確覆蓋，測試使用精確斷言
b. **如果是 K 線與 timeframe 不整除導致尾部遺失**：修正切分邏輯後，使用 `assert len(trades) >= expected - margin` 或更精確的邏輯
c. **如果是平行化 race condition**：修復共享狀態問題

**注意事項：**
- **不要簡單地將 `== 1440` 改成 `>= 1430`** — 必須先理解根因
- 修復後確保在多次連續執行時穩定通過（至少連跑 5 次不失敗）
- 如果根因是平行化本身的不確定性（如 thread scheduling），則需要在引擎層解決，而非在測試層放寬

**驗收：**
```bash
# 連跑 5 次確認穩定
for i in $(seq 1 5); do uv run pytest tests/test_backtest_engine.py::test_run_backtest_basic -v; done
```

---

### G2.3.0.3 — 運維穩健性：run_live_supervised.sh

**新增檔案：** `scripts/run_live_supervised.sh`

建立一個 supervisor shell script，功能：

1. **自動重啟**：`run_live.py` crash 時自動重啟，並帶指數退避（初始 5s, 最高 300s）
2. **日誌輪替**：輸出到 `logs/live_YYYYMMDD.log`，每天一個新檔，避免單一 log 檔過大
3. **健康監控**：寫入 PID 到 `logs/live.pid`，方便外部監控或 kill
4. **優雅停止**：trap SIGTERM/SIGINT，先向 Python 進程送 SIGINT，等待 10 秒後 SIGKILL
5. **最大重啟次數**：1 小時內最多重啟 10 次，超過則停止並報錯

**腳本框架：**

```bash
#!/bin/bash
# scripts/run_live_supervised.sh — Supervised live runner with auto-restart

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
PID_FILE="$LOG_DIR/live.pid"

RESTART_DELAY=5
MAX_RESTART_DELAY=300
MAX_RESTARTS_PER_HOUR=10

mkdir -p "$LOG_DIR"

cleanup() {
    # Kill child process gracefully
    if [ -n "${CHILD_PID:-}" ] && kill -0 "$CHILD_PID" 2>/dev/null; then
        kill -INT "$CHILD_PID"
        # Wait up to 10 seconds for graceful shutdown
        for i in $(seq 1 10); do
            kill -0 "$CHILD_PID" 2>/dev/null || break
            sleep 1
        done
        # Force kill if still alive
        kill -0 "$CHILD_PID" 2>/dev/null && kill -9 "$CHILD_PID"
    fi
    rm -f "$PID_FILE"
    echo "[supervisor] Stopped."
    exit 0
}

trap cleanup SIGINT SIGTERM

restart_count=0
restart_window_start=$(date +%s)

while true; do
    LOG_FILE="$LOG_DIR/live_$(date +%Y%m%d).log"
    
    echo "[supervisor] Starting run_live.py at $(date)" | tee -a "$LOG_FILE"
    
    cd "$PROJECT_DIR"
    uv run python scripts/run_live.py "$@" >> "$LOG_FILE" 2>&1 &
    CHILD_PID=$!
    echo "$CHILD_PID" > "$PID_FILE"
    
    wait "$CHILD_PID" || true
    EXIT_CODE=$?
    
    echo "[supervisor] run_live.py exited with code $EXIT_CODE at $(date)" | tee -a "$LOG_FILE"
    
    # Rate limit restarts
    now=$(date +%s)
    elapsed=$((now - restart_window_start))
    if [ "$elapsed" -gt 3600 ]; then
        restart_count=0
        restart_window_start=$now
    fi
    
    restart_count=$((restart_count + 1))
    if [ "$restart_count" -ge "$MAX_RESTARTS_PER_HOUR" ]; then
        echo "[supervisor] ERROR: Too many restarts ($restart_count in ${elapsed}s). Stopping." | tee -a "$LOG_FILE"
        rm -f "$PID_FILE"
        exit 1
    fi
    
    echo "[supervisor] Restarting in ${RESTART_DELAY}s... (attempt $restart_count)" | tee -a "$LOG_FILE"
    sleep "$RESTART_DELAY"
    
    # Exponential backoff
    RESTART_DELAY=$((RESTART_DELAY * 2))
    if [ "$RESTART_DELAY" -gt "$MAX_RESTART_DELAY" ]; then
        RESTART_DELAY=$MAX_RESTART_DELAY
    fi
done
```

**使用方式：**
```bash
# 前台運行（含所有策略）
bash scripts/run_live_supervised.sh

# 背景運行
nohup bash scripts/run_live_supervised.sh &

# 帶參數（傳遞給 run_live.py）
bash scripts/run_live_supervised.sh --strategies lgbm_v2,catboost_v1

# 查看 PID
cat logs/live.pid

# 停止
kill $(cat logs/live.pid)
# 或者直接 kill supervisor 自己（它會 cleanup 子進程）
```

**驗收：**
```bash
# 腳本存在且可執行
test -f scripts/run_live_supervised.sh

# 語法檢查
bash -n scripts/run_live_supervised.sh

# 快速功能驗證（dry-run 模式，應正常退出後嘗試重啟，再 Ctrl+C 停止）
timeout 15 bash scripts/run_live_supervised.sh --dry-run || true
```

---

### G2.3.0.4 — 新增 logs/ 到 .gitignore

**檔案：** `.gitignore`

新增：
```
logs/
```

確認 `logs/` 不會被 commit。

**驗收：**
```bash
grep "logs/" .gitignore
```

---

### G2.3.0.5 — 測試

**新增/修改檔案：** `tests/test_backtest_engine.py`（修改）

除了 G2.3.0.2 的修復外，不需新增額外測試檔案。

**驗收：**
```bash
# 所有測試通過
uv run pytest -v

# Backtest 測試穩定
for i in $(seq 1 5); do uv run pytest tests/test_backtest_engine.py -v; done
```

---

## 執行順序

```
G2.3.0.0（PROGRESS.md 同步）— 最先，純文件操作
  ↓
G2.3.0.1（ARCHITECTURE.md 同步）— 純文件操作
  ↓
G2.3.0.2（Flaky Test 修復）— 需要閱讀理解 backtest engine 邏輯
  ↓
G2.3.0.4（.gitignore 更新）— 預備 logs 目錄
  ↓
G2.3.0.3（run_live_supervised.sh）— 最後，創建新腳本
  ↓
G2.3.0.5（驗證）— 全部跑一次
```

---

## 修改範圍（封閉清單）

**新增：**
- `scripts/run_live_supervised.sh` — Supervised live runner

**修改：**
- `docs/PROGRESS.md` — 標記 2.4.1、2.4.2 完成
- `docs/ARCHITECTURE.md` — 補充 `get_settled_signals` 介面
- `tests/test_backtest_engine.py` — 修復 flaky test
- `.gitignore` — 新增 `logs/`

**不動：**
- `docs/DECISIONS.md` — 不修改
- `config/project_constants.yaml` — 不修改
- `src/btc_predictor/` — 所有 source code 不動
- `scripts/run_live.py` — 不修改（supervisor 是外層 wrapper）
- `src/btc_predictor/backtest/engine.py` — 視 G2.3.0.2 根因分析決定是否需修改（若需修改，也在封閉清單內）
- 現有 Discord 指令不動
- 現有 Signal Layer / Settler 不動

---

## 介面契約

本 task 不新增跨模組介面。

唯一的介面變更是在 `ARCHITECTURE.md` 中**文件化** `get_settled_signals()`，此方法已在 G2.2.1 中實作完成。

---

## 不要做的事

- **不要修改 `run_live.py` 的邏輯**（supervisor 是外層 wrapper，不動 Python 層）
- **不要修改 prediction_signals 或 simulated_trades 的 schema**
- **不要修改策略邏輯或特徵工程**
- **不要修改 Discord Bot 指令邏輯**
- **不要在 flaky test 修復中「放寬斷言」來掩蓋根因** — 先理解根因再修
- **不要引入新的 Python 依賴**
- **不要修改 `project_constants.yaml`**
- **不要使用 systemd 或 Docker** — 目前階段用 shell supervisor 即可
- **不要建立新的 Python 模組**（本 task 唯一新增的是 shell script）

---

## 停止條件

完成 G2.3.0.0 → G2.3.0.5 後停下，將所有產出帶回給架構師。

**架構師會根據結果決定：**
- 如果所有測試穩定通過 + supervisor 腳本可用 → 部署 supervised mode，開始 24h 穩定性驗證
- 如果 backtest flaky test 的根因在 engine.py → 需評估是否影響回測結果的準確性

---

## 驗收標準（按順序執行）

```bash
# 0. PROGRESS.md 2.4.1、2.4.2 已勾選
grep "\[x\].*2.4.1" docs/PROGRESS.md
grep "\[x\].*2.4.2" docs/PROGRESS.md

# 1. ARCHITECTURE.md 包含 get_settled_signals
grep "get_settled_signals" docs/ARCHITECTURE.md

# 2. Flaky Test 穩定通過（至少跑 3 次）
for i in $(seq 1 3); do uv run pytest tests/test_backtest_engine.py::test_run_backtest_basic -v || exit 1; done

# 3. Supervisor 腳本存在
test -f scripts/run_live_supervised.sh
bash -n scripts/run_live_supervised.sh

# 4. logs/ 在 .gitignore 中
grep "logs/" .gitignore

# 5. 所有測試通過
uv run pytest -v
```

---

## Coding Agent 回報區

### 實作結果
1. **文件同步**：已更新 `docs/PROGRESS.md` (2.4.1, 2.4.2) 與 `docs/ARCHITECTURE.md` (`get_settled_signals`)。
2. **Flaky Test 修復**：修復了 `src/btc_predictor/backtest/engine.py` 中的 `_process_fold`。
   - **問題根因**：多執行緒環境下共享 `ohlcv` DataFrame 導致 `loc` 切片在並發訪問時偶發性返回空值或不完整資料（可能是 Pandas DatetimeIndex 的內部快取競爭）。
   - **修復方案**：在每個 fold 處理開始時，根據需要的时间窗口對 `ohlcv` 進行 `.copy()`，使其成為該執行緒私有的資料塊。
   - **驗證**：Repro 腳本連跑 50 次全數通過，`pytest` 連跑 5 次全數通過。
3. **運維穩健性**：新增 `scripts/run_live_supervised.sh`。
   - 實現了指數退避重啟。
   - 實現了按日期輪替的日誌系統 (`logs/live_YYYYMMDD.log`)。
   - 實現了 PID 記錄與優雅停止 (SIGINT -> SIGKILL)。
4. **.gitignore**：已將 `logs/` 加入忽略清單。

### 驗證自檢
- [PASS] 0. PROGRESS.md 2.4.1、2.4.2 已勾選
- [PASS] 1. ARCHITECTURE.md 包含 get_settled_signals
- [PASS] 2. Flaky Test 穩定通過（已跑 5 次 + 50 次專屬測試）
- [PASS] 3. Supervisor 腳本存在且語法正確
- [PASS] 4. logs/ 在 .gitignore 中
- [PASS] 5. 所有測試通過 (71 passed)

### 遇到的問題
- **PYTHONPATH 環境變數**：部分測試使用 `from src.btc_predictor` 而部分使用 `from btc_predictor`，導致在不同環境下可能報 `ModuleNotFoundError`。建議未來統一 import 路徑。目前以 `PYTHONPATH=.:src` 解決。
- **YAML 並發讀取**：雖然本次修復主要在於 DataFrame，但理論上多執行緒頻繁讀取同一 YAML 亦有風險。未來若系統規模擴大，建議在 `engine.py` 外層先加載好 constants 再傳入。

### PROGRESS.md 修改建議
- 無，已按 spec 要求同步完成。下一步建議開啟「24小時穩定性驗證」任務。

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
