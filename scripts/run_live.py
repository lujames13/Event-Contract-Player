import asyncio
import signal
import os
import sys
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from binance import AsyncClient

# Add src to sys.path to allow imports from btc_predictor
sys.path.append(str(Path(__file__).parent.parent / "src"))

from btc_predictor.data.store import DataStore
from btc_predictor.data.pipeline import DataPipeline
from btc_predictor.simulation.settler import settle_pending_trades
from btc_predictor.strategies.registry import StrategyRegistry
from btc_predictor.utils.config import load_constants
from btc_predictor.discord_bot.bot import EventContractBot

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("run_live")

async def settler_loop(store: DataStore, client: AsyncClient, bot: EventContractBot = None):
    """Periodic task to settle pending trades."""
    while True:
        try:
            # Await the async settle_pending_trades
            await settle_pending_trades(store, client, bot=bot)
        except Exception as e:
            logger.error(f"Error in settler_loop: {e}", exc_info=True)
        await asyncio.sleep(60)

async def main():
    parser = argparse.ArgumentParser(description="BTC Predictor Live System")
    parser.add_argument("--strategies", type=str, help="Comma-separated list of strategies to load (e.g. lgbm_v2,catboost_v1)")
    parser.add_argument("--timeframes", type=str, help="Comma-separated list of timeframes to enable (e.g. 10,60)")
    parser.add_argument("--dry-run", action="store_true", help="Run a single prediction then exit")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    discord_token = os.getenv("DISCORD_TOKEN")
    discord_channel_id = os.getenv("DISCORD_CHANNEL_ID")
    
    # 1. Init DataStore
    store = DataStore()
    
    # 2. Discover strategies
    registry = StrategyRegistry()
    registry.discover(
        strategies_dir=Path("src/btc_predictor/strategies"),
        models_dir=Path("models")
    )

    all_strategies = registry.list_strategies()
    
    # Filter by --strategies
    if args.strategies:
        target_names = [s.strip() for s in args.strategies.split(",")]
        strategies = [s for s in all_strategies if s.name in target_names]
        # Check if any strategy requested was not found
        found_names = [s.name for s in strategies]
        for name in target_names:
            if name not in found_names:
                logger.warning(f"Strategy '{name}' requested but not found or could not be loaded.")
    else:
        strategies = all_strategies

    # Filter to only strategies that have models
    strategies = [s for s in strategies if s.available_timeframes]
    
    if not strategies:
        logger.error("No valid strategies with models found. Exiting.")
        return

    logger.info("="*60)
    logger.info("Loaded Strategies:")
    final_strategies = []
    enabled_timeframes = {} # strategy_name -> list[int]
    
    for s in strategies:
        tfs = s.available_timeframes
        if args.timeframes:
            requested_tfs = [int(tf.strip()) for tf in args.timeframes.split(",")]
            tfs = [tf for tf in tfs if tf in requested_tfs]
        
        if tfs:
            logger.info(f" - {s.name:15} | Timeframes: {tfs}")
            final_strategies.append(s)
            enabled_timeframes[s.name] = tfs
        else:
            logger.debug(f" - {s.name:15} | No matching timeframes enabled.")
    
    if not final_strategies:
        logger.error("No strategies enabled for the selected timeframes. Exiting.")
        return
        
    logger.info("="*60)

    # 3. Dry-run Mode
    if args.dry_run:
        logger.info("Running in DRY-RUN mode.")
        df = store.get_latest_ohlcv("BTCUSDT", "1m", limit=500)
        if df.empty:
            logger.error("No data in DB to perform dry-run. Please fetch some data first.")
            return
            
        for s in final_strategies:
            tfs = enabled_timeframes[s.name]
            for tf in tfs:
                try:
                    pred_signal = s.predict(df, tf)
                    logger.info(f"DRY-RUN | {s.name:10} | {tf:4}m | Dir: {pred_signal.direction:6} | Conf: {pred_signal.confidence:.4f} | Price: {pred_signal.current_price}")
                except Exception as e:
                    logger.error(f"DRY-RUN | {s.name:10} | {tf:4}m | Error: {e}")
        logger.info("Dry-run completed.")
        return

    # 4. Setup Binance Clients
    client = await AsyncClient.create(api_key, api_secret)
    
    # 5. Setup Discord Bot
    bot = None
    if discord_token and discord_channel_id:
        guild_id = os.getenv("DISCORD_GUILD_ID")
        bot = EventContractBot(
            channel_id=int(discord_channel_id),
            guild_id=int(guild_id) if guild_id else None
        )
        bot.store = store
        asyncio.create_task(bot.start(discord_token))
        logger.info(f"Discord Bot task started.")
    
    # 6. Setup Pipeline
    # Pass both strategies and enabled_timeframes context if needed?
    # Actually, pipeline.py currently triggers ALL timeframes. 
    # G2.0.2 will fix this in pipeline.py to only trigger available_timeframes.
    pipeline = DataPipeline("BTCUSDT", ["1m"], final_strategies, store, bot=bot)
    if bot:
        bot.pipeline = pipeline
    
    # 7. Handle Shutdown
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    
    def shutdown():
        logger.info("Shutting down...")
        stop_event.set()
        
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown)
        
    # 8. Run tasks
    tasks = [
        asyncio.create_task(pipeline.start()),
        asyncio.create_task(settler_loop(store, client, bot=bot))
    ]
    
    logger.info("Live simulation started. Press Ctrl+C to stop.")
    await stop_event.wait()
    
    # Cleanup
    await pipeline.stop()
    if bot:
        await bot.close()
    await client.close_connection()
    for task in tasks:
        task.cancel()
    
    logger.info("Live simulation stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
