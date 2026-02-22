import asyncio
import signal
import os
import sys
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add src to sys.path to allow imports from btc_predictor
sys.path.append(str(Path(__file__).parent.parent / "src"))

from btc_predictor.infrastructure.store import DataStore
from btc_predictor.binance.feed import BinanceFeed
from btc_predictor.strategies.registry import StrategyRegistry
from btc_predictor.polymarket.gamma_client import GammaClient
from btc_predictor.polymarket.tracker import PolymarketTracker
from btc_predictor.polymarket.pipeline import PolymarketLivePipeline

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("run_live")

async def main() -> None:
    parser = argparse.ArgumentParser(description="Polymarket Live Paper Trading Engine")
    parser.add_argument(
        "--strategies",
        type=str,
        help="Comma-separated list of strategies to load (e.g. pm_v1)",
        default="pm_v1"
    )
    args = parser.parse_args()

    load_dotenv()
    
    logger.info("Starting Polymarket Live Pipeline...")

    # 1. Init DataStore
    store = DataStore()

    # 2. Discover strategies
    registry = StrategyRegistry()
    registry.discover(
        strategies_dir=Path("src/btc_predictor/strategies"),
        models_dir=Path("models"),
    )

    all_strategies = registry.list_strategies()

    # Filter by --strategies
    target_names = [s.strip() for s in args.strategies.split(",")]
    strategies = [s for s in all_strategies if s.name in target_names]
    found_names = [s.name for s in strategies]
    for name in target_names:
        if name not in found_names:
            logger.warning(
                f"Strategy '{name}' requested but not found or could not be loaded."
            )

    # Keep only strategies that have at least one trained model
    strategies = [s for s in strategies if hasattr(s, 'available_timeframes') and s.available_timeframes]

    if not strategies:
        logger.error("No valid strategies with models found. Exiting.")
        return

    logger.info("=" * 60)
    logger.info("Loaded Strategies:")
    for s in strategies:
        logger.info(f" - {s.name:15} | Timeframes: {s.available_timeframes}")
    logger.info("=" * 60)

    # 3. Setup Polymarket Components
    # For now, we only need GammaClient for public read-only requests. No CLOB API key needed yet.
    gamma_client = GammaClient()
    tracker = PolymarketTracker(gamma_client=gamma_client, store=store)

    # 4. Instantiate BinanceFeed and PolymarketLivePipeline
    # BinanceFeed is used to supply high-frequency OHLCV features
    feed = BinanceFeed(symbol="BTCUSDT", store=store)
    pipeline = PolymarketLivePipeline(strategies=strategies, store=store, tracker=tracker)

    # 5. Wire feed -> pipeline
    feed.register_callback(pipeline.process_new_data)
    pipeline._feed = feed

    # 6. Handle graceful shutdown
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def shutdown() -> None:
        logger.info("Shutting down gracefully...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown)

    # 7. Run feed + tracker concurrently
    tasks = [
        asyncio.create_task(feed.start()),
        asyncio.create_task(pipeline.run_tracker()),
    ]

    logger.info("Live simulation started. Press Ctrl+C to stop.")
    await stop_event.wait()

    # Cleanup
    await feed.stop()
    
    for task in tasks:
        task.cancel()

    logger.info("Polymarket live simulation stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
