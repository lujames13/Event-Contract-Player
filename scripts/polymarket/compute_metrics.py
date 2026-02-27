import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
import yaml
import warnings

# Suppress pandas FutureWarnings and others for lean CLI output
warnings.simplefilter(action='ignore', category=FutureWarning)

from btc_predictor.analytics.extractors import (
    get_signal_dataframe, get_trade_dataframe, get_market_context, join_signals_with_context
)
from btc_predictor.analytics.metrics import (
    compute_directional_accuracy, compute_pnl_metrics, compute_alpha_analysis,
    compute_temporal_patterns, compute_confidence_calibration, compute_drift_detection
)

logger = logging.getLogger(__name__)

def load_breakeven_winrate(config_path="config/project_constants.yaml") -> float:
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
            return config.get("polymarket", {}).get("breakeven_winrate", {}).get("maker", 0.500)
    except Exception:
        return 0.500

def main():
    parser = argparse.ArgumentParser(description="Compute Polymarket metrics")
    parser.add_argument("--strategy", type=str, help="Strategy name to filter")
    parser.add_argument("--timeframe", type=int, help="Timeframe minutes to filter")
    parser.add_argument("--days", type=int, help="Number of days to look back")
    parser.add_argument("-o", "--output", type=str, default="reports/polymarket/metrics.json", help="Output JSON path")
    parser.add_argument("--db-path", type=str, default="data/btc_predictor.db", help="Database path")
    args = parser.parse_args()

    breakeven_winrate = load_breakeven_winrate()
    now_str = datetime.now(timezone.utc).isoformat()

    out_dir = Path(args.output).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # Base meta
    meta = {
        "generated_at": now_str,
        "db_path": args.db_path,
        "filters": {
            "strategy": args.strategy,
            "timeframe": args.timeframe,
            "days": args.days
        },
        "data_range": {
            "first_signal": None,
            "last_signal": None,
            "total_signals": 0,
            "settled_signals": 0
        },
        "breakeven_winrate": breakeven_winrate
    }

    # Base empty metrics structure
    metrics = {
        "meta": meta,
        "directional_accuracy": {},
        "pnl": {},
        "alpha": {},
        "temporal": {},
        "calibration": {},
        "drift": {},
        "gate3_status": {
            "da_above_breakeven": False,
            "trades_above_200": False,
            "pnl_positive": False,
            "pipeline_72h_stable": None,
            "overall": "NOT_PASSED"
        }
    }

    signals_df = get_signal_dataframe(args.db_path, args.strategy, args.timeframe, settled_only=True, days=args.days)
    trades_df = get_trade_dataframe(args.db_path, args.strategy, args.days) # timeframe filter handled via signal JOIN logic or here

    if signals_df.empty:
        print("Insufficient data: No settled signals found.")
        with open(args.output, "w") as f:
            json.dump(metrics, f, indent=2)
        print("Gate3 Status: NOT_PASSED | DA: 0.00% | PnL: $0.00")
        return

    # Filter trades by timeframe if specified (as get_trade_dataframe returns s.timeframe_minutes)
    if not trades_df.empty and args.timeframe:
        trades_df = trades_df[trades_df['timeframe_minutes'] == args.timeframe]

    meta["data_range"]["first_signal"] = signals_df['timestamp'].min().isoformat()
    meta["data_range"]["last_signal"] = signals_df['timestamp'].max().isoformat()
    meta["data_range"]["total_signals"] = len(signals_df)
    meta["data_range"]["settled_signals"] = len(signals_df)

    # Fetch context and join
    try:
        timestamps = signals_df['timestamp'].tolist()
        context_df = get_market_context(args.db_path, timestamps)
        analysis_df = join_signals_with_context(signals_df, context_df)
    except Exception as e:
        logger.warning(f"Could not merge context: {e}")
        analysis_df = signals_df

    da_metrics = compute_directional_accuracy(analysis_df, groupby=['timeframe_minutes'] if not args.timeframe else None)
    metrics["directional_accuracy"] = da_metrics

    pnl_metrics = compute_pnl_metrics(trades_df)
    metrics["pnl"] = pnl_metrics

    alpha_metrics = compute_alpha_analysis(analysis_df)
    metrics["alpha"] = alpha_metrics

    temporal_metrics = compute_temporal_patterns(analysis_df)
    metrics["temporal"] = temporal_metrics

    calib_metrics = compute_confidence_calibration(analysis_df)
    metrics["calibration"] = calib_metrics

    drift_metrics = compute_drift_detection(analysis_df)
    metrics["drift"] = drift_metrics

    # Gate 3 status
    da_val = da_metrics.get("overall", {}).get("da", 0.0)
    da_above_breakeven = da_val > breakeven_winrate
    trades_above_200 = pnl_metrics.get("total_trades", 0) >= 200
    pnl_positive = pnl_metrics.get("total_pnl", 0.0) > 0.0
    
    metrics["gate3_status"]["da_above_breakeven"] = da_above_breakeven
    metrics["gate3_status"]["trades_above_200"] = trades_above_200
    metrics["gate3_status"]["pnl_positive"] = pnl_positive
    
    if da_above_breakeven and trades_above_200 and pnl_positive:
        metrics["gate3_status"]["overall"] = "PASSED (requires manual 72h check)"

    with open(args.output, "w") as f:
        json.dump(metrics, f, indent=2)

    status = metrics["gate3_status"]["overall"]
    da_pct = da_val * 100
    pnl_val = pnl_metrics.get("total_pnl", 0.0)
    
    print(f"Gate3 Status: {status} | DA: {da_pct:.2f}% | PnL: ${pnl_val:.2f}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
