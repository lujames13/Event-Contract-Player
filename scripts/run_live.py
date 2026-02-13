import asyncio
import signal
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from binance.client import Client

# Add src to sys.path to allow imports from btc_predictor
sys.path.append(str(Path(__file__).parent.parent / "src"))

from btc_predictor.data.store import DataStore
from btc_predictor.data.pipeline import DataPipeline
from btc_predictor.simulation.settler import settle_pending_trades


def check_model_exists(model_path: str) -> bool:
    """檢查模型檔案是否存在"""
    path = Path(model_path)
    if not path.exists():
        print(f"❌ 模型檔案不存在: {model_path}")
        print(f"   請先執行: python scripts/train_xgboost_model.py")
        return False
    print(f"✅ 找到模型檔案: {model_path}")
    return True

from btc_predictor.strategies.xgboost_direction.strategy import XGBoostDirectionStrategy

from btc_predictor.utils.config import load_constants
from btc_predictor.discord_bot.bot import EventContractBot

async def settler_loop(store: DataStore, client: Client, bot: EventContractBot = None):
    """
    Periodic task to settle pending trades.
    """
    while True:
        try:
            # Pass bot to settle_pending_trades so it can notify
            settle_pending_trades(store, client, bot=bot)
        except Exception as e:
            print(f"Error in settler_loop: {e}")
        await asyncio.sleep(60) # Check every minute

async def main():
    load_dotenv()
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    discord_token = os.getenv("DISCORD_TOKEN")
    discord_channel_id = os.getenv("DISCORD_CHANNEL_ID")
    
    # 1. Init DataStore
    store = DataStore()
    
    # 2. Setup Discord Bot if token available
    bot = None
    if discord_token and discord_channel_id:
        guild_id = os.getenv("DISCORD_GUILD_ID")
        bot = EventContractBot(
            channel_id=int(discord_channel_id),
            guild_id=int(guild_id) if guild_id else None
        )
        bot.store = store
        asyncio.create_task(bot.start(discord_token))
        print(f"Discord Bot task started. (Guild sync: {'Yes' if guild_id else 'Global'})")
    
    # 3. Setup Binance Clients
    client = Client(api_key, api_secret)
    
    # Initialize strategies with pre-trained models
    MODEL_PATH = "models/xgboost_10m.pkl"  # 預設使用 10 分鐘模型

    if not check_model_exists(MODEL_PATH):
        print("\n⚠️  未找到預訓練模型，策略將無法運作")
        print("   1. 執行 'python scripts/train_xgboost_model.py' 訓練模型")
        print("   2. 或者註解掉此策略的初始化\n")
        exit(1)

    print(f"🤖 載入 XGBoost 策略（模型: {MODEL_PATH}）")
    xgb_strategy = XGBoostDirectionStrategy(model_path=MODEL_PATH)

    strategies = [xgb_strategy]
    
    # 5. Setup Pipeline
    constants = load_constants()
    symbol = "BTCUSDT"
    intervals = ["1m"]
    
    # Pass bot to pipeline so it can send signals
    pipeline = DataPipeline(symbol, intervals, strategies, store, bot=bot)
    
    # 6. Handle Shutdown
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    
    print("Starting real-time prediction system...")
    print("\n" + "="*60)
    print("即時預測系統啟動")
    print("="*60)
    print(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"監控商品: BTCUSDT")
    print(f"監控時間框架: 1m")
    print("="*60 + "\n")

    def shutdown():
        print("Shutting down...")
        stop_event.set()
        
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown)
        
    # 7. Run tasks
    tasks = [
        asyncio.create_task(pipeline.start()),
        asyncio.create_task(settler_loop(store, client, bot=bot))
    ]
    
    print("Live simulation started. Press Ctrl+C to stop.")
    await stop_event.wait()
    
    # Cleanup
    await pipeline.stop()
    if bot:
        await bot.close()
    for task in tasks:
        task.cancel()
    
    print("Live simulation stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
