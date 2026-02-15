# Task Spec: [PROGRESS.md 任務編號，如 1.6.2]
<!-- status: draft | in-progress | review | done | blocked -->
<!-- created: YYYY-MM-DD -->
<!-- architect: Claude Opus (Chat Project) -->

## 目標

一句話說明此任務要達成什麼。
對應 PROGRESS.md: Phase X > Task X.Y.Z

## 修改範圍

需要修改的檔案：
- `src/btc_predictor/...` — 說明改什麼
- `tests/...` — 說明測什麼

不可修改的檔案：
- `docs/DECISIONS.md`
- `config/project_constants.yaml`
- （其他此任務不應碰的檔案）

## 實作要求

具體的技術要求。粒度標準：coding agent 讀完後不需要做架構層級的判斷。

## 不要做的事

- 不要 ...
- 不要 ...

## 介面契約

引用 ARCHITECTURE.md 中相關的 dataclass/介面：
- 輸入：...
- 輸出：...

## 驗收標準

1. `uv run pytest tests/...` 全部通過
2. ...
3. ...

---

## Coding Agent 回報區

### 實作結果
<!-- 完成了什麼，修改了哪些檔案 -->

### 驗收自檢
<!-- 逐條列出驗收標準的 pass/fail -->

### 遇到的問題
<!-- 技術障礙、設計疑慮 -->

### PROGRESS.md 修改建議
<!-- 如果實作過程中發現規劃需要調整，在此說明 -->

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