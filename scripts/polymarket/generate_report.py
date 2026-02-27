import argparse
import json
import sys
from pathlib import Path


def render_report(data: dict) -> str:
    """Render the metrics dictionary into a Markdown report."""
    
    lines = []
    
    # Overview / Meta
    meta = data.get("meta", {})
    gen_time = meta.get("generated_at", "N/A")
    data_range = meta.get("data_range", {})
    filters = meta.get("filters", {})
    
    lines.append("# Polymarket Metrics Report")
    lines.append("")
    lines.append("## 📊 Overview / Meta")
    lines.append(f"- **Generated At**: `{gen_time}`")
    lines.append("- **Filters**:")
    for k, v in filters.items():
        lines.append(f"  - {k}: `{v}`")
    lines.append("- **Data Range**:")
    lines.append(f"  - First Signal: `{data_range.get('first_signal', 'N/A')}`")
    lines.append(f"  - Last Signal: `{data_range.get('last_signal', 'N/A')}`")
    lines.append(f"  - Total Signals: `{data_range.get('total_signals', 'N/A')}`")
    lines.append(f"  - Settled Signals: `{data_range.get('settled_signals', 'N/A')}`")
    lines.append("")
    
    # Concept Drift
    drift = data.get("drift", {})
    is_degrading = drift.get("is_degrading", False)
    if is_degrading:
        lines.append("> 🚨 **WARNING: CONCEPT DRIFT DETECTED (Model is degrading)**")
        lines.append("")
        
    # Gate 3 Status
    gate3 = data.get("gate3_status", {})
    lines.append("## 🚦 Gate 3 Status")
    
    overall = gate3.get('overall', 'UNKNOWN')
    overall_icon = "✅" if overall == "PASSED" else "❌"
    lines.append(f"**Overall Status: {overall_icon} {overall}**")
    lines.append("")
    
    def bool_icon(v):
        if v is True: return "✅"
        if v is False: return "❌"
        return "❓"
        
    lines.append("| Criterion | Status |")
    lines.append("|-----------|--------|")
    lines.append(f"| DA Above Breakeven | {bool_icon(gate3.get('da_above_breakeven'))} |")
    lines.append(f"| Trades >= 200 | {bool_icon(gate3.get('trades_above_200'))} |")
    lines.append(f"| PnL Positive | {bool_icon(gate3.get('pnl_positive'))} |")
    lines.append(f"| Pipeline 72h Stable | {bool_icon(gate3.get('pipeline_72h_stable'))} |")
    lines.append("")
    
    # Core Metrics (DA & PnL)
    lines.append("## 🎯 Core Metrics (DA & PnL)")
    da = data.get("directional_accuracy", {})
    overall_da = da.get("overall", {})
    pnl = data.get("pnl", {})
    
    lines.append("### Directional Accuracy")
    lines.append(f"- **Overall DA**: `{overall_da.get('da', 0.0):.2%}` (Total: {overall_da.get('total', 0)}, Correct: {overall_da.get('correct', 0)})")
    
    lines.append("")
    lines.append("#### By Timeframe")
    lines.append("| Timeframe | DA | Total | Correct |")
    lines.append("|-----------|----|-------|---------|")
    by_group = da.get("by_group", {})
    for tf, metrics in by_group.items():
        lines.append(f"| {tf}m | {metrics.get('da', 0.0):.2%} | {metrics.get('total', 0)} | {metrics.get('correct', 0)} |")
    lines.append("")
    
    lines.append("### Profit & Loss (PnL)")
    lines.append(f"- **Total PnL**: `${pnl.get('total_pnl', 0.0):.2f}`")
    lines.append(f"- **Total Trades**: `{pnl.get('total_trades', 0)}`")
    lines.append(f"- **Win Rate**: `{pnl.get('win_rate', 0.0):.2%}`")
    lines.append(f"- **Profit Factor**: `{pnl.get('profit_factor', 0.0):.2f}`")
    lines.append(f"- **Max Drawdown**: `${pnl.get('max_drawdown', 0.0):.2f}` ({pnl.get('max_drawdown_pct', 0.0):.2%})")
    lines.append(f"- **Avg Win**: `${pnl.get('avg_win', 0.0):.2f}` / **Avg Loss**: `${pnl.get('avg_loss', 0.0):.2f}`")
    lines.append("")
    
    # Alpha Analysis & Temporal
    lines.append("## 📈 Alpha Analysis & Temporal")
    
    alpha = data.get("alpha", {})
    alpha_dist = alpha.get("distribution", {})
    lines.append("### Alpha Distribution")
    lines.append(f"- Mean: `{alpha_dist.get('mean', 0.0):.4f}`")
    lines.append(f"- Median: `{alpha_dist.get('median', 0.0):.4f}`")
    lines.append(f"- Std: `{alpha_dist.get('std', 0.0):.4f}`")
    lines.append(f"- Min: `{alpha_dist.get('min', 0.0):.4f}` / Max: `{alpha_dist.get('max', 0.0):.4f}`")
    lines.append("")
    
    temporal = data.get("temporal", {})
    recent = temporal.get("recent_vs_all", {})
    lines.append("### Temporal Trend (Recent vs All-Time)")
    lines.append("| Period | DA | Total Signals |")
    lines.append("|--------|----|---------------|")
    for period in ["last_7d", "last_30d", "all_time"]:
        p_data = recent.get(period, {})
        lines.append(f"| {period} | {p_data.get('da', 0.0):.2%} | {p_data.get('total', 0)} |")
    lines.append("")
    
    # Calibration
    calibration = data.get("calibration", {})
    lines.append("## ⚖️ Calibration")
    lines.append(f"- **Brier Score**: `{calibration.get('brier_score', 0.0):.4f}`")
    lines.append(f"- **Baseline Brier**: `{calibration.get('baseline_brier', 0.0):.4f}`")
    lines.append("")
    
    # Drift details
    lines.append("## 🌊 Concept Drift Details")
    lines.append(f"- **Is Degrading**: `{is_degrading}`")
    lines.append(f"- **Trend Slope**: `{drift.get('trend_slope', 0.0):.6f}` per window")
    best_w = drift.get("best_window", {})
    worst_w = drift.get("worst_window", {})
    if best_w:
        lines.append(f"- **Best Window DA**: `{best_w.get('da', 0.0):.2%}` (idx {best_w.get('start_idx', '?')} to {best_w.get('end_idx', '?')})")
    if worst_w:
        lines.append(f"- **Worst Window DA**: `{worst_w.get('da', 0.0):.2%}` (idx {worst_w.get('start_idx', '?')} to {worst_w.get('end_idx', '?')})")
        
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate Markdown report from metrics.json")
    parser.add_argument(
        "--input", 
        type=str, 
        default="reports/polymarket/metrics.json",
        help="Path to input metrics.json file"
    )
    parser.add_argument(
        "--output", 
        type=str, 
        default="reports/polymarket/metrics_report.md",
        help="Path to output Markdown report file"
    )
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    
    if not input_path.exists():
        print(f"Error: Input file '{input_path}' does not exist.", file=sys.stderr)
        sys.exit(1)
        
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON format in '{input_path}': {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading '{input_path}': {e}", file=sys.stderr)
        sys.exit(1)
        
    md_content = render_report(data)
    
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"Report successfully generated at: {output_path}")
    except Exception as e:
        print(f"Error writing to '{output_path}': {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
