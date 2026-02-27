#!/bin/bash
# scripts/start_pm_live.sh
# 這個腳本用來在後台執行 Polymarket 的 run_live.py，並將日誌輸出到 logs 資料夾

# 取得專案根目錄
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/pm_live_$(date +%Y%m%d).log"

# 確保 logs 資料夾存在
mkdir -p "$LOG_DIR"

cd "$PROJECT_DIR"

# 檢查是否已經在執行
if pgrep -f "python scripts/run_live.py" > /dev/null; then
    echo "⚠️ Polymarket run_live.py 已經在執行中了！"
    echo "可使用 'ps aux | grep run_live.py' 查看詳細 PID。"
    exit 0
fi

echo "🚀 開始在後台執行 Polymarket run_live.py..."
# 在後台執行，加上 nohup 防斷線
nohup env PYTHONPATH=src uv run python scripts/run_live.py > "$LOG_FILE" 2>&1 &
PID=$!

echo "✅ 執行成功！"
echo "📌 PID: $PID"
echo "📄 日誌路徑: $LOG_FILE"
echo "💡 提示: 你可以使用以下指令即時查看日誌："
echo "   tail -f $LOG_FILE"
echo "💡 提示: 若要關閉程序，請執行:\n   kill $PID"
