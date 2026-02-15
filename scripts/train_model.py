
import argparse
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

# Setup path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from btc_predictor.data.store import DataStore
from btc_predictor.strategies.registry import StrategyRegistry
from btc_predictor.strategies.base import BaseStrategy

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

STRATEGIES_DIR = Path("src/btc_predictor/strategies")
MODELS_DIR = Path("models")

def train_strategy(strategy: BaseStrategy, timeframe: int, store: DataStore):
    logger.info(f"Training {strategy.name} for {timeframe}m timeframe...")
    
    # Load data (60 days)
    # Ideally should be configurable or strategy-dependent logic?
    # Task spec says: 60 days of 1 min data
    days = 60
    limit = days * 24 * 60
    
    # We load latest data
    df = store.get_ohlcv("BTCUSDT", "1m", limit=limit)
    
    if df.empty or len(df) < 1000:
        logger.error(f"Insufficient data for {strategy.name} ({len(df)} rows)")
        return False
        
    try:
        if strategy.requires_fitting:
            strategy.fit(df, timeframe)
            logger.info(f"Fitted {strategy.name} {timeframe}m successfully.")
            
            # Save model
            model_path = MODELS_DIR / strategy.name / f"{timeframe}m.pkl"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            
            if hasattr(strategy, "save_model"):
                strategy.save_model(timeframe, str(model_path))
                logger.info(f"Saved model to {model_path}")
                return True
            else:
                logger.warning(f"Strategy {strategy.name} does not have save_model method. Skipping save.")
                return False
        else:
            logger.info(f"Strategy {strategy.name} does not require fitting.")
            return True
            
    except Exception as e:
        logger.error(f"Error training {strategy.name} {timeframe}m: {e}", exc_info=True)
        return False

def main():
    parser = argparse.ArgumentParser(description="Train Event Contract Strategies")
    parser.add_argument("--strategy", type=str, help="Specific strategy name")
    parser.add_argument("--timeframe", type=int, help="Specific timeframe (10, 30, 60, 1440)")
    parser.add_argument("--all", action="store_true", help="Train all default timeframes (10, 30, 60, 1440)")
    parser.add_argument("--all-strategies", action="store_true", help="Train all available strategies")
    
    args = parser.parse_args()
    
    if not (args.strategy or args.all_strategies):
        parser.error("Must specify --strategy or --all-strategies")
        
    if not (args.timeframe or args.all):
        parser.error("Must specify --timeframe or --all")
        
    # Init Registry
    registry = StrategyRegistry()
    registry.discover(STRATEGIES_DIR, MODELS_DIR)
    
    # Determine strategies
    strategies_to_train: List[BaseStrategy] = []
    if args.all_strategies:
        strategies_to_train = registry.list_strategies()
    else:
        try:
            strategies_to_train = [registry.get(args.strategy)]
        except KeyError:
            logger.error(f"Strategy {args.strategy} not found. Available: {registry.list_names()}")
            sys.exit(1)
            
    # Determine timeframes
    timeframes = []
    if args.all:
        timeframes = [10, 30, 60, 1440]
    else:
        timeframes = [args.timeframe]
        
    # Execution
    store = DataStore()
    
    success_count = 0
    total_tasks = len(strategies_to_train) * len(timeframes)
    
    for strat in strategies_to_train:
        for tf in timeframes:
            if train_strategy(strat, tf, store):
                success_count += 1
                
    logger.info(f"Training complete. {success_count}/{total_tasks} successful.")

if __name__ == "__main__":
    main()
