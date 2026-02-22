import asyncio
import logging
import uuid
import json
from typing import Any, List
from datetime import datetime, timedelta

import pandas as pd

from btc_predictor.infrastructure.store import DataStore
from btc_predictor.strategies.base import BaseStrategy
from btc_predictor.polymarket.tracker import PolymarketTracker
from btc_predictor.models import PredictionSignal, SimulatedTrade, PolymarketOrder
from btc_predictor.utils.config import load_constants

logger = logging.getLogger(__name__)

# Trigger map for Polymarket timeframes
TRIGGER_MAP = {
    5: lambda dt: (dt.minute + 1) % 5 == 0,
    15: lambda dt: (dt.minute + 1) % 15 == 0,
    60: lambda dt: (dt.minute + 1) % 60 == 0,
    240: lambda dt: (dt.hour * 60 + dt.minute + 1) % 240 == 0,
    1440: lambda dt: dt.hour == 23 and dt.minute == 59,
}

class PolymarketLivePipeline:
    def __init__(
        self,
        strategies: List[BaseStrategy],
        store: DataStore,
        tracker: PolymarketTracker,
    ) -> None:
        self.strategies = strategies
        self.store = store
        self.tracker = tracker
        self.trigger_count: int = 0
        self._feed: Any = None
        
        constants = load_constants()
        self.alpha_thresholds = constants.get("alpha_thresholds", {})
        self.risk_cfg = constants.get("risk_control", {})
        self.pm_cfg = constants.get("polymarket", {})

    @property
    def is_running(self) -> bool:
        if self._feed is not None:
            return self._feed.is_running
        return False

    @property
    def last_kline_time(self) -> dict:
        if self._feed is not None:
            return self._feed._last_kline_time
        return {}

    async def process_new_data(self, ohlcv: pd.DataFrame) -> None:
        if ohlcv.empty:
            return

        latest_dt = ohlcv.index[-1]

        for timeframe, trigger_fn in TRIGGER_MAP.items():
            if trigger_fn(latest_dt):
                await self._trigger_strategies(ohlcv, timeframe)

    async def run_tracker(self) -> None:
        """Periodic background task to sync active markets."""
        timeframes = self.pm_cfg.get("initial_focus", [5, 15])
        while True:
            try:
                await self.tracker.sync_active_markets(timeframes=timeframes)
            except Exception as e:
                logger.error(f"PolymarketLivePipeline tracker error: {e}", exc_info=True)
            await asyncio.sleep(60)

    async def _trigger_strategies(self, ohlcv: pd.DataFrame, timeframe: int) -> None:
        self.trigger_count += 1
        logger.info(f"PolymarketLivePipeline: Triggering strategies for {timeframe}m…")

        for strategy in self.strategies:
            if timeframe not in strategy.available_timeframes:
                continue

            try:
                # 1. Prediction (CPU-intensive — offloaded to thread)
                signal: PredictionSignal = await asyncio.to_thread(strategy.predict, ohlcv, timeframe)

                # 2. Decision & Simulate Stage
                pm_market = self.tracker.get_active_market(timeframe)
                
                market_price = None
                market_slug = None
                
                if pm_market:
                    market_slug = pm_market.get("slug")
                    market_price_up = pm_market.get("close_price")
                    if market_price_up is not None:
                        if signal.direction == "higher":
                            market_price = market_price_up
                        else:
                            market_price = 1.0 - market_price_up
                        
                        signal.market_slug = market_slug
                        signal.market_price_up = market_price_up
                        signal.alpha = signal.confidence - market_price

                # Check Risk (daily loss, max trades, consecutive losses)
                from btc_predictor.simulation.risk import should_trade
                
                from datetime import timezone
                # Get stats for today
                today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                daily_stats = self.store.get_daily_stats(strategy.name, today_str)
                can_trade = should_trade(
                    daily_stats.get("daily_loss", 0.0),
                    daily_stats.get("consecutive_losses", 0),
                    daily_stats.get("daily_trades", 0)
                )

                strat_threshold = self.alpha_thresholds.get(strategy.name)
                if isinstance(strat_threshold, dict):
                    threshold = strat_threshold.get(timeframe)
                else:
                    threshold = strat_threshold
                        
                threshold = threshold if threshold is not None else 0.02
                
                trade = None
                order = None
                trade_id = None
                order_id = None
                bet_amount = float(self.risk_cfg.get("bet_range", [10, 100])[0])

                should_bet = signal.alpha is not None and signal.alpha > threshold and can_trade

                if should_bet:
                    trade_id = str(uuid.uuid4())
                    
                    # Convert pandas timestamp to standard datetime to avoid timezone issues/bugs
                    timestamp_dt = signal.timestamp
                    if isinstance(timestamp_dt, pd.Timestamp):
                        timestamp_dt = timestamp_dt.to_pydatetime()
                        
                    expiry_dt = timestamp_dt + timedelta(minutes=timeframe)
                        
                    trade = SimulatedTrade(
                        id=trade_id,
                        strategy_name=strategy.name,
                        direction=signal.direction,
                        confidence=signal.confidence,
                        timeframe_minutes=signal.timeframe_minutes,
                        bet_amount=bet_amount,
                        open_time=timestamp_dt,
                        open_price=signal.current_price,
                        expiry_time=expiry_dt,
                        features_used=signal.features_used
                    )
                    
                    side = "BUY"
                    up_token_id = pm_market.get("up_token_id") if pm_market else "mock_token_up"
                    down_token_id = pm_market.get("down_token_id") if pm_market else "mock_token_down"
                    token_id = up_token_id if signal.direction == "higher" else down_token_id
                    
                    order_id = str(uuid.uuid4())
                    order = PolymarketOrder(
                        signal_id="PLACEHOLDER", # Will be replaced
                        order_id=order_id,
                        token_id=token_id,
                        side=side,
                        price=market_price if market_price else 0.5,
                        size=bet_amount / (market_price if market_price else 0.5),
                        order_type="GTC",
                        status="OPEN",
                        placed_at=timestamp_dt
                    )

                # Execute transaction using DataStore connection
                try:
                    self.store.save_polymarket_execution_context(signal, trade, order)
                    if should_bet and trade and order:
                        logger.info(f"PolymarketLivePipeline: Placed SimulatedTrade {trade.id} and PolymarketOrder {order.order_id} for {strategy.name} ({timeframe}m)")

                except Exception as e:
                    logger.error(f"PolymarketLivePipeline: DB Transaction error: {e}", exc_info=True)

            except Exception as e:
                logger.error(f"PolymarketLivePipeline: Error triggering {strategy.name} for {timeframe}m: {e}", exc_info=True)

