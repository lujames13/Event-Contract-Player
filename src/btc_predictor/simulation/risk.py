from btc_predictor.utils.config import load_constants

def should_trade(daily_loss: float, consecutive_losses: int, daily_trades: int) -> bool:
    """
    Check if a trade should be allowed based on risk control rules.
    
    Args:
        daily_loss: Total loss accumulated today in USDT.
        consecutive_losses: Number of consecutive losses in the current streak.
        daily_trades: Total number of trades made today.
        
    Returns:
        bool: True if trade is allowed, False otherwise.
    """
    constants = load_constants()
    risk_cfg = constants.get("risk_control", {})
    
    # 1. Daily max loss check
    max_loss = risk_cfg.get("daily_max_loss", 50)
    if daily_loss >= max_loss:
        return False
        
    # 2. Max daily trades check
    max_trades = risk_cfg.get("max_daily_trades", 30)
    if daily_trades >= max_trades:
        return False
        
    # 3. Consecutive losses check
    # Note: The requirement says "max_consecutive_losses: 8 # 連敗 N 筆暫停 1 小時"
    # For now, we return False if it's hit. The 1-hour pause logic might be handled by the caller
    # or we might need more state. Simple check for now.
    max_consecutive = risk_cfg.get("max_consecutive_losses", 8)
    if consecutive_losses >= max_consecutive:
        return False
        
    return True

def calculate_bet(confidence: float, timeframe_minutes: int) -> float:
    """
    Calculate the bet amount based on confidence level and timeframe.
    
    Args:
        confidence: Prediction confidence (0.0 ~ 1.0).
        timeframe_minutes: Timeframe in minutes.
        
    Returns:
        float: Bet amount in USDT.
    """
    constants = load_constants()
    risk_cfg = constants.get("risk_control", {})
    thresholds = constants.get("confidence_thresholds", {})
    
    # Get threshold for the timeframe
    threshold = thresholds.get(timeframe_minutes, 0.6) # Default to 0.6 if not found
    
    # If confidence is below threshold, bet is 0 (or should_trade handles this?)
    # Usually, if we call calculate_bet, we expect a trade. 
    # But let's check against threshold anyway.
    if confidence < threshold:
        return 0.0
        
    bet_range = risk_cfg.get("bet_range", [5, 20])
    min_bet = bet_range[0]
    max_bet = bet_range[1]
    
    # "confidence_to_bet": "linear" # 閾值→5, 1.0→20
    # Map [threshold, 1.0] to [min_bet, max_bet]
    if confidence >= 1.0:
        return float(max_bet)
    
    # Linear interpolation:
    # bet = min_bet + (max_bet - min_bet) * (confidence - threshold) / (1.0 - threshold)
    bet = min_bet + (max_bet - min_bet) * (confidence - threshold) / (1.0 - threshold)
    
    # Clamp to range just in case
    bet = max(float(min_bet), min(float(max_bet), bet))
    
    return round(bet, 2)
