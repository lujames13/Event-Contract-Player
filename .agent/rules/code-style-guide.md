---
trigger: always_on
---

# Repo Instruction — Event-Contract-Player

> 這份 instruction 補充 AGENTS.md 的操作規範，提供 coding quality 層面的規則。
> AGENTS.md = 你要做什麼、怎麼做；這份 = 寫程式時要注意什麼。

## 開工流程

每次開始新任務前：
1. 讀 `docs/PROGRESS.md` 確認當前狀態
2. 讀 `docs/DECISIONS.md` 確認不可變約束
3. 如果任務涉及跨模組介面，讀 `docs/ARCHITECTURE.md` 中的介面契約

## 程式碼品質規則

### Error Handling

所有網路 I/O（Binance REST API、WebSocket、Discord）必須有明確的錯誤處理：
- 使用 try/except 捕獲具體異常（不要裸 `except Exception`）
- 網路請求必須設定 timeout
- WebSocket 斷線必須有重連機制（exponential backoff）
- 失敗時 log 完整的錯誤資訊（含 traceback），不要靜默吞掉

```python
# ✓ 正確
try:
    resp = await client.get(url, timeout=10)
    resp.raise_for_status()
except httpx.TimeoutException:
    logger.warning("Binance API timeout, retrying...", exc_info=True)
    # retry logic
except httpx.HTTPStatusError as e:
    logger.error(f"Binance API error: {e.response.status_code}")
    raise

# ✗ 錯誤
try:
    resp = await client.get(url)
except Exception:
    pass
```

### 時間序列紀律（最重要）

這是預測系統，前視偏差會直接導致回測結果無效：
- 特徵計算只能使用 t 時刻及之前的數據
- Label 生成邏輯（`labeling.py`）是核心，修改前必須通知人類
- 任何涉及時間索引的操作，確認是否包含或排除端點（closed/open interval）
- DataFrame 操作後用 `.sort_index()` 確保時間順序
- 禁止在 feature 計算中使用 `.shift(-n)`（負數 shift = 未來數據）

### SQLite 注意事項

- 所有寫入操作使用 transaction（`with conn:` 或明確的 BEGIN/COMMIT）
- 長時間運行的讀取不要持有 connection，讀完就關
- WAL mode 已啟用，但寫入仍然是序列化的——不要假設可以並行寫入
- UPSERT 使用 `INSERT ... ON CONFLICT ... DO UPDATE`

### Async 規範

- 不要在 async 函數中呼叫阻塞操作（如 `time.sleep()`、同步 I/O）
- 使用 `asyncio.sleep()` 替代 `time.sleep()`
- CPU-intensive 操作（模型推理、特徵計算）使用 `asyncio.to_thread()` 或 `loop.run_in_executor()`
- WebSocket listener 和模型推理應在不同的 task 中運行

### Type Hints & Dataclass

- 所有函數簽名必須有 type hints
- 使用 `docs/ARCHITECTURE.md` 定義的 dataclass（PredictionSignal、SimulatedTrade）作為跨模組輸出
- 不要自行定義替代的 data structure 來繞過介面契約
- `Literal` types 要與 ARCHITECTURE.md 保持一致（如 `Literal["higher", "lower"]`）

## 測試規範

- 每個新模組在 `tests/` 對應路徑下建立測試
- 測試命名：`test_<function_name>_<scenario>`
- 時間序列相關測試必須包含邊界情況：缺失數據、平盤、跨日
- 數值比較使用 `pytest.approx()` 而非 `==`
- 不要 mock 核心邏輯（如 label 生成、信心度計算），只 mock 外部依賴（API call、file I/O）

## Config 管理

- 所有可調參數從 `config/project_constants.yaml` 讀取
- 不要在程式碼中硬編碼閾值、下注金額、API URL 等
- 如果需要新的 config 參數，加到 yaml 並在 commit message 中說明

## Commit 與進度

- Commit message 格式：`[phase-X.Y] 簡述`
- 完成任務後更新 `docs/PROGRESS.md`（詳見 AGENTS.md）
- 一個 commit 做一件事，不要把多個不相關的修改混在一起