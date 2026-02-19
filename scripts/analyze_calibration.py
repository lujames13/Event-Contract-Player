#!/usr/bin/env python3
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd
from btc_predictor.data.store import DataStore

# Constants (matching DECISIONS.md and Task Spec)
CONFIDENCE_THRESHOLDS = {10: 0.606, 30: 0.591, 60: 0.591, 1440: 0.591}
PAYOUT_RATIOS = {10: 1.80, 30: 1.85, 60: 1.85, 1440: 1.85}
BREAKEVEN_WINRATES = {10: 0.5556, 30: 0.5405, 60: 0.5405, 1440: 0.5405}

def estimate_avg_bet(confidence_values: pd.Series, threshold: float) -> float:
    """計算在給定閾值下，通過的 signal 的平均下注金額。"""
    bets = []
    for conf in confidence_values:
        if conf >= threshold:
            # 線性映射：閾值 -> 5, 1.0 -> 20
            bet = 5 + (conf - threshold) / (1.0 - threshold) * 15
            bets.append(min(20, max(5, bet)))
    return np.mean(bets) if bets else 0.0

def run_calibration_analysis(df: pd.DataFrame, min_samples: int) -> str:
    """執行完整校準分析並返回報告文字。"""
    if df.empty:
        return "無數據可供分析。"

    strategy = df['strategy_name'].iloc[0] if len(df['strategy_name'].unique()) == 1 else "All"
    timeframe = df['timeframe_minutes'].iloc[0] if len(df['timeframe_minutes'].unique()) == 1 else "All"
    total_settled = len(df)
    
    report = []
    report.append(f"=== 校準分析報告 ===")
    report.append(f"生成時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"策略: {strategy} | Timeframe: {timeframe} | 已結算: {total_settled} 筆\n")

    if total_settled < 50:
        report.append("⚠️ 警告：已結算 signal < 50 筆，分析結果僅供參考。\n")

    # --- 分析一：校準曲線 (Reliability Diagram) ---
    report.append("=== 校準曲線 (Calibration Curve) ===")
    bins = [
        (0.50, 0.52), (0.52, 0.54), (0.54, 0.56), (0.56, 0.58), (0.58, 0.60),
        (0.60, 0.65), (0.65, 0.70), (0.70, 0.80), (0.80, 1.01)
    ]
    
    bin_results = []
    ece = 0.0
    
    report.append(f"{'Confidence Bin':<18} | {'Mean Conf':<9} | {'Actual Acc':<10} | {'Count':<5} | {'判定'}")
    report.append("-" * 70)
    
    prev_acc = -1.0
    confidence_inversion = False
    
    for start, end in bins:
        mask = (df['confidence'] >= start) & (df['confidence'] < end)
        bin_df = df[mask]
        count = len(bin_df)
        
        if count == 0:
            continue
            
        mean_conf = bin_df['confidence'].mean()
        actual_acc = bin_df['is_correct'].mean()
        
        # ECE calculation: sum(count_i / total * abs(actual_acc_i - mean_conf_i))
        ece += (count / total_settled) * abs(actual_acc - mean_conf)
        
        status = ""
        if count < min_samples:
            status = "⚠️ 樣本不足"
        elif abs(actual_acc - mean_conf) < 0.05:
            status = "✅ 校準良好"
        elif actual_acc > mean_conf + 0.05:
            status = "🔵 過度保守"
        else:
            status = "⚠️ 過度自信"
            
        if prev_acc > actual_acc + 0.02 and count >= min_samples: # Allow some noise if samples are low
            confidence_inversion = True
            status += " | ❌ 信心反轉"
            
        prev_acc = actual_acc
        report.append(f"[{start:.2f}, {end:.2f}){'' if end < 1 else ' ':<7} | {mean_conf:.3f}     | {actual_acc*100:6.2f}%    | {count:5} | {status}")

    report.append(f"\n完美校準線: y = x（對角線）")
    report.append(f"ECE (Expected Calibration Error): {ece:.4f}\n")

    # --- 分析二：最佳閾值搜尋 ---
    report.append("=== 最佳閾值搜尋 (Optimal Threshold Search) ===")
    
    # Needs payout info
    if timeframe == "All":
        report.append("無法在混合 timeframe 下搜尋最佳閾值，請使用 --timeframe 篩選。\n")
    else:
        payout = PAYOUT_RATIOS.get(timeframe, 1.85)
        breakeven = BREAKEVEN_WINRATES.get(timeframe, 0.5405)
        current_threshold = CONFIDENCE_THRESHOLDS.get(timeframe, 0.591)
        
        report.append(f"Payout: {payout}x | Breakeven: {breakeven*100:.2f}%\n")
        report.append(f"{'Threshold':<10} | {'Signals':<7} | {'Accuracy':<8} | {'E[PnL/trade]':<12} | {'E[trades/day]':<12} | {'E[PnL/day]':<10} | {'判定'}")
        report.append("-" * 95)
        
        # Calculate observe duration for frequency
        ts_min = pd.to_datetime(df['timestamp']).min()
        ts_max = pd.to_datetime(df['timestamp']).max()
        duration_days = max(0.1, (ts_max - ts_min).total_seconds() / 86400)
        
        best_pnl_day = -999.0
        best_threshold = 0.5
        current_pnl_day = 0.0
        
        thresholds = np.arange(0.50, 0.71, 0.01)
        for t in thresholds:
            passed_signals = df[df['confidence'] >= t]
            count = len(passed_signals)
            
            if count == 0:
                continue
                
            acc = passed_signals['is_correct'].mean()
            avg_bet = estimate_avg_bet(passed_signals['confidence'], t)
            
            # expected_pnl_per_trade = accuracy * (payout - 1) * avg_bet - (1 - accuracy) * avg_bet
            # Simplifies to: accuracy * payout * avg_bet - avg_bet = avg_bet * (accuracy * payout - 1)
            expected_pnl_trade = avg_bet * (acc * payout - 1)
            
            trades_per_day = count / duration_days
            expected_pnl_day = expected_pnl_trade * trades_per_day
            
            is_current = abs(t - current_threshold) < 0.005
            star = "★" if is_current else " "
            
            status = "✅ 正 EV" if expected_pnl_trade > 0 else "❌ 負 EV"
            if count < min_samples:
                status = "⚠️ 樣本不足"
            
            report.append(f"{t:.2f} {star:<2}   | {count:7} | {acc*100:6.2f}%  | {expected_pnl_trade:+11.2f}  | {trades_per_day:12.1f} | {expected_pnl_day:+10.2f} | {status}")
            
            if status != "⚠️ 樣本不足" and expected_pnl_day > best_pnl_day:
                best_pnl_day = expected_pnl_day
                best_threshold = t
            
            if is_current:
                current_pnl_day = expected_pnl_day

        report.append(f"\n★ 最佳閾值（最大化 E[PnL/day]）: {best_threshold:.2f} → E[PnL/day] = {best_pnl_day:+.2f}")
        report.append(f"★ 當前閾值 {current_threshold:.3f}: E[PnL/day] = {current_pnl_day:+.2f}")
        if current_pnl_day > 0 and best_pnl_day > current_pnl_day:
            improvement = (best_pnl_day / current_pnl_day - 1) * 100
            report.append(f"★ 潛在改善: {improvement:+.1f}%")
        
        report.append("\n⚠️ 注意：此分析基於樣本，統計顯著性有限。建議累積 ≥ 200 筆後重新評估。\n")

    # --- 分析三：時間窗口演化 ---
    report.append("=== 時間窗口演化 (Time Window Evolution) ===")
    if total_settled < 50:
        report.append("跳過：樣本不足，需 ≥ 50 筆已結算 signal。\n")
    else:
        window_size = 30
        step = 10
        report.append(f"Window: {window_size} signals, Step: {step}\n")
        report.append(f"{'Window':<12} | {'Period':<35} | {'Accuracy':<8} | {'Trend'}")
        report.append("-" * 75)
        
        windows_acc = []
        for i in range(0, total_settled - window_size + 1, step):
            win_df = df.iloc[i : i + window_size]
            acc = win_df['is_correct'].mean()
            windows_acc.append(acc)
            
            start_ts = pd.to_datetime(win_df['timestamp']).min().strftime('%Y-%m-%d %H:%M')
            end_ts = pd.to_datetime(win_df['timestamp']).max().strftime('%Y-%m-%d %H:%M')
            
            trend = ""
            if len(windows_acc) > 1:
                diff = windows_acc[-1] - windows_acc[-2]
                trend = f"{'↑' if diff > 0 else '↓'} {diff*100:+.2f}%"
            
            report.append(f"#{i//step + 1:<10} | {start_ts} ~ {end_ts[-5:]} | {acc*100:6.2f}%  | {trend}")
            
        if len(windows_acc) >= 2:
            x = np.arange(len(windows_acc))
            slope, _ = np.polyfit(x, windows_acc, 1)
            slope_pct = slope * 100
            
            drift_status = "📊 穩定"
            if slope_pct < -2:
                drift_status = "⚠️ 下降趨勢"
            elif slope_pct > 2:
                drift_status = "🔵 上升趨勢"
            
            report.append(f"\n線性迴歸斜率: {slope_pct:.2f}%/window → {drift_status}")
        report.append("")

    # --- 分析四：連續信號一致性 ---
    report.append("=== 連續信號一致性 (Consecutive Signal Consistency) ===")
    df_sorted = df.sort_values('timestamp')
    
    baseline_acc = df_sorted['is_correct'].mean()
    
    report.append(f"{'連續次數':<10} | {'方向':<6} | {'出現次數':<8} | {'最後一筆正確率':<14} | {'對比基線'}")
    report.append("-" * 70)
    
    for n in [2, 3, 4, 5]:
        sequences = []
        # Find sequences of N consecutive signals with same direction
        # strategy and timeframe should be unique for this analysis to make sense
        if (strategy == "All" or timeframe == "All") and n == 2:
            report.append(f"(此分析僅在單一策略及單一 timeframe 下有意義)")
            break
            
        current_dir = None
        current_count = 0
        
        for idx, row in df_sorted.iterrows():
            if row['direction'] == current_dir:
                current_count += 1
            else:
                current_dir = row['direction']
                current_count = 1
            
            if current_count >= n:
                sequences.append(row['is_correct'])
        
        if not sequences:
            continue
            
        seq_acc = np.mean(sequences)
        status = ""
        if len(sequences) < min_samples:
            status = "⚠️ 樣本不足"
        else:
            diff = seq_acc - baseline_acc
            status = f"{diff*100:+.2f}% vs 基線 {baseline_acc*100:.2f}%"
            
        report.append(f"{n} 連續{' ':4} | {'same':<6} | {len(sequences):8} | {seq_acc*100:12.2f}% | {status}")
    
    report.append("\n結論: 連續同方向信號對正確率之影響分析。即使目前樣本不足，框架已建立。\n")

    # --- 綜合建議 ---
    report.append("=== 綜合建議 ===")
    
    # 1. 閾值
    if timeframe != "All":
        pnl_diff = best_pnl_day - current_pnl_day
        if total_settled < 100: report.append("1. 閾值調整建議：⚠️ 統計信心不足")
        elif total_settled < 200: report.append("1. 閾值調整建議：建議累積更多數據後重新評估")
        else:
            if best_threshold != current_threshold and pnl_diff > 0.1:
                report.append(f"1. 閾值調整建議：可考慮更新 project_constants.yaml 至 {best_threshold:.2f}")
            else:
                report.append("1. 閾值調整建議：當前閾值合理")
    
    # 2. 校準
    if ece < 0.05:
        report.append(f"2. 模型校準狀態：ECE = {ece:.4f} (良好)")
    else:
        report.append(f"2. 模型校準狀態：ECE = {ece:.4f} (需要校準)")
        
    if confidence_inversion:
        report.append("   ❌ 高信心區存在反轉，建議重新訓練模型或加入後校準")

    # 3. Drift
    if total_settled >= 50:
        if slope_pct < -2:
            report.append("3. Drift 狀態：⚠️ 偵測到表現下降趨勢，建議確認是否為 concept drift")
        else:
            report.append("3. Drift 狀態：模型表現穩定，無需介入")
    
    # 4. 下一步
    report.append("4. 下一步：")
    report.append(f"   - 累積 {'≥ 200' if total_settled < 200 else '更多'} 筆後重新跑本腳本")
    if timeframe != "All" and total_settled >= 200 and best_threshold != current_threshold:
         report.append(f"   - 如果最佳閾值穩定，可考慮更新 project_constants.yaml")

    return "\n".join(report)

def main():
    parser = argparse.ArgumentParser(description="Calibration Analysis Tool")
    parser.add_argument("--strategy", type=str, help="Filter by strategy name")
    parser.add_argument("--timeframe", type=int, help="Filter by timeframe in minutes")
    parser.add_argument("--output", type=str, default="reports/calibration/", help="Output directory")
    parser.add_argument("--min-samples", type=int, default=10, help="Minimum samples for calibration bin")
    args = parser.parse_args()

    store = DataStore()
    df = store.get_settled_signals(strategy_name=args.strategy, timeframe_minutes=args.timeframe)

    if df.empty:
        print(f"在資料庫中找不到已結算的訊號 (Strategy={args.strategy}, Timeframe={args.timeframe})")
        return

    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Run analysis
    report_text = run_calibration_analysis(df, args.min_samples)

    # Print to stdout
    print(report_text)

    # Save to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"calibration_analysis_{timestamp}.txt"
    with open(output_dir / filename, "w", encoding="utf-8") as f:
        f.write(report_text)
    
    print(f"\n報告已儲存至: {output_dir / filename}")

if __name__ == "__main__":
    main()
