import pandas as pd
import numpy as np

def calculate_fees(p, size=50.0):
    # Formula from search: fee = size * 0.25 * (p * (1-p))^2
    # But wait, is size the investment or the number of shares?
    # If size is investment I:
    # N = I / p
    # fee = N * 0.25 * (p * (1-p))^2 = (I/p) * 0.25 * p^2 * (1-p)^2 = I * 0.25 * p * (1-p)^2
    
    # Let's use the formula: fee = N * 0.25 * (p * (1-p))^2
    # At p=0.5, I=$50, N=100 shares.
    # fee = 100 * 0.25 * (0.5 * 0.5)^2 = 100 * 0.25 * 0.0625 = 1.5625
    # Investment = 50. Fee rate = 1.5625 / 50 = 3.125%
    
    N = size / p
    fee = N * 0.25 * (p * (1-p))**2
    effective_fee_rate = fee / size
    
    # Breakeven win rate (W)
    # W * (N - size - fee) + (1-W) * (-size - fee) = 0
    # W*N - W*size - W*fee - size - fee + W*size + W*fee = 0
    # W*N = size + fee
    # W = (size + fee) / N = (size + fee) / (size/p) = p * (1 + fee/size)
    
    breakeven_winrate = p * (1 + effective_fee_rate)
    
    return fee, effective_fee_rate * 100, breakeven_winrate * 100

def main():
    prices = [0.05, 0.1, 0.2, 0.3, 0.4, 0.45, 0.5, 0.55, 0.6, 0.7, 0.8, 0.9, 0.95]
    results = []
    
    binance_breakeven_10m = 55.56
    binance_breakeven_60m = 54.05
    
    for p in prices:
        fee, eff_rate, be_wr = calculate_fees(p)
        results.append({
            "Entry Price": p,
            "Position ($50)": 50.0,
            "Taker Fee ($)": round(fee, 4),
            "Effective Fee Rate (%)": round(eff_rate, 2),
            "Breakeven Win Rate (%)": round(be_wr, 2),
            "Binance EC 10m Breakeven (%)": binance_breakeven_10m,
            "Difference (%)": round(be_wr - binance_breakeven_10m, 2)
        })
        
    df = pd.DataFrame(results)
    print(df.to_string(index=False))
    
    # Save to report later
    df.to_csv("reports/polymarket/fee_table.csv", index=False)

if __name__ == "__main__":
    main()
