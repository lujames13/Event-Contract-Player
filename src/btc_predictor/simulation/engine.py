import uuid
from datetime import datetime, timedelta
from btc_predictor.models import PredictionSignal, SimulatedTrade
from btc_predictor.simulation.risk import should_trade, calculate_bet
from btc_predictor.data.store import DataStore

def process_signal(signal: PredictionSignal, store: DataStore) -> SimulatedTrade | None:
    """
    Process a new prediction signal: risk check, bet sizing, and persistence.
    """
    # 1. Get daily stats for risk control
    # Use signal timestamp (UTC)
    now = signal.timestamp if signal.timestamp else datetime.utcnow()
    
    date_str = now.strftime("%Y-%m-%d")
    stats = store.get_daily_stats(signal.strategy_name, date_str)
    
    # 2. Risk check
    allowed = should_trade(
        daily_loss=stats["daily_loss"],
        consecutive_losses=stats["consecutive_losses"],
        daily_trades=stats["daily_trades"]
    )
    
    if not allowed:
        print(f"[{signal.strategy_name}] Trade skipped due to risk control.")
        return None
        
    # 3. Calculate bet
    bet = calculate_bet(signal.confidence, signal.timeframe_minutes)
    
    if bet <= 0:
        return None
        
    # 4. Create SimulatedTrade
    trade = SimulatedTrade(
        id=str(uuid.uuid4()),
        strategy_name=signal.strategy_name,
        direction=signal.direction,
        confidence=signal.confidence,
        timeframe_minutes=signal.timeframe_minutes,
        bet_amount=float(bet),
        open_time=signal.timestamp,
        open_price=signal.current_price,
        expiry_time=signal.timestamp + timedelta(minutes=signal.timeframe_minutes),
        features_used=signal.features_used
    )
    
    # 5. Persist to DB
    store.save_simulated_trade(trade)
    print(f"[{signal.strategy_name}] Created simulated trade: {trade.direction} {trade.bet_amount} USDT")
    
    return trade
