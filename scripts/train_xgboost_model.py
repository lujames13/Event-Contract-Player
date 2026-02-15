"""
DEPRECATED: This script is deprecated. Use scripts/train_model.py instead.

訓練 XGBoost 方向預測模型並儲存

功能:
1. 從 SQLite 資料庫載入 BTCUSDT 的 1 分鐘 K 線數據（過去 60 天）
2. 訓練三個模型分別預測 10/30/60 分鐘後的價格方向
3. 儲存模型至 models/ 目錄
4. 印出訓練集準確率供驗證

使用範例:
    python scripts/train_xgboost_model.py
    python scripts/train_xgboost_model.py --timeframe 10  # 只訓練 10 分鐘模型
"""

from datetime import datetime, timedelta
import argparse
import os
import sys
from pathlib import Path

# Add src to sys.path to allow imports from btc_predictor
sys.path.append(str(Path(__file__).parent.parent / "src"))

from btc_predictor.data.store import DataStore
from btc_predictor.strategies.xgboost_v1.model import XGBoostDirectionModel


def train_model(timeframe_minutes: int, data_store: DataStore, output_dir: Path):
    """訓練單一時間框架的模型"""
    
    print(f"\n{'='*60}")
    print(f"訓練 {timeframe_minutes} 分鐘方向預測模型")
    print(f"{'='*60}")
    
    # 1. 載入數據（過去 60 天的 1 分鐘數據）
    print("📊 載入訓練數據...")
    days = 60
    limit = days * 24 * 60  # 60 天 * 24 小時 * 60 分鐘
    
    df = data_store.get_ohlcv(
        symbol="BTCUSDT",
        interval="1m",
        limit=limit
    )
    
    if df is None or len(df) < 1000:
        print(f"❌ 數據不足（需要至少 1000 條，目前 {len(df) if df is not None else 0} 條）")
        return False
    
    print(f"✅ 載入 {len(df)} 條數據（時間範圍: {df.index[0]} ~ {df.index[-1]}）")
    
    # 2. 訓練模型
    print(f"🤖 開始訓練...")
    model = XGBoostDirectionModel()
    
    try:
        accuracy = model.fit(df, timeframe_minutes=timeframe_minutes)
        print(f"✅ 訓練完成 - 訓練集準確率: {accuracy:.2%}")
    except Exception as e:
        print(f"❌ 訓練失敗: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 3. 儲存模型
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / f"xgboost_v1/{timeframe_minutes}m.pkl"
    
    # Ensure subdirectory exists
    model_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"💾 儲存模型至 {model_path}")
    model.save(str(model_path))
    
    # 4. 驗證模型可載入
    print(f"🔍 驗證模型載入...")
    test_model = XGBoostDirectionModel()
    test_model.load(str(model_path))
    print(f"✅ 模型驗證成功")
    
    return True


def main():
    parser = argparse.ArgumentParser(description="訓練 XGBoost 方向預測模型")
    parser.add_argument(
        "--timeframe",
        type=int,
        choices=[10, 30, 60],
        help="指定訓練的時間框架（分鐘），不指定則訓練全部"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/btc_predictor.db",
        help="SQLite 資料庫路徑"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="models",
        help="模型輸出目錄"
    )
    
    args = parser.parse_args()
    
    # 初始化
    data_store = DataStore(args.db_path)
    output_dir = Path(args.output_dir)
    
    print(f"\n🚀 XGBoost 模型訓練程序")
    print(f"資料庫: {args.db_path}")
    print(f"輸出目錄: {output_dir}")
    
    # 訓練模型
    timeframes = [args.timeframe] if args.timeframe else [10, 30, 60]
    
    results = {}
    for tf in timeframes:
        success = train_model(tf, data_store, output_dir)
        results[tf] = success
    
    # 總結
    print(f"\n{'='*60}")
    print(f"訓練總結")
    print(f"{'='*60}")
    for tf, success in results.items():
        status = "✅ 成功" if success else "❌ 失敗"
        print(f"{tf} 分鐘模型: {status}")
    
    all_success = all(results.values())
    if all_success:
        print(f"\n🎉 所有模型訓練完成！")
        print(f"\n下一步: 執行 'python scripts/run_live.py' 測試即時預測")
    else:
        print(f"\n⚠️  部分模型訓練失敗，請檢查錯誤訊息")
    
    return 0 if all_success else 1


if __name__ == "__main__":
    exit(main())
