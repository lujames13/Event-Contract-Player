import pandas as pd
import numpy as np
import argparse
import sys
from pathlib import Path
from lightgbm import LGBMClassifier

# Setup path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from btc_predictor.data.store import DataStore
from btc_predictor.strategies.xgboost_v1.features import generate_features, get_feature_columns
from btc_predictor.data.labeling import add_direction_labels

def main():
    parser = argparse.ArgumentParser(description="Feature Importance Analysis")
    parser.add_argument("--timeframe", type=int, default=10, help="Timeframe")
    parser.add_argument("--days", type=int, default=180, help="Days")
    
    args = parser.parse_args()
    
    store = DataStore()
    limit = args.days * 24 * 60
    # To get LATEST data, we need to order DESC and then reverse
    query = f"SELECT * FROM ohlcv WHERE symbol = 'BTCUSDT' AND interval = '1m' ORDER BY open_time DESC LIMIT {limit}"
    with store._get_connection() as conn:
        df = pd.read_sql_query(query, conn)
    
    if df.empty:
        print("No data found")
        return
        
    df['datetime'] = pd.to_datetime(df['open_time'], unit='ms', utc=True)
    df.set_index('datetime', inplace=True)
    df = df.sort_index() # Revert to ASC for indicator calculation
    
    feat_df = generate_features(df)
    labeled_df = add_direction_labels(feat_df, args.timeframe)
    feature_cols = get_feature_columns()
    labeled_df = labeled_df.dropna(subset=["label"] + feature_cols)
    
    X = labeled_df[feature_cols]
    y = labeled_df["label"]
    
    model = LGBMClassifier(n_jobs=-1, verbose=-1, importance_type='gain')
    model.fit(X, y)
    
    importances = pd.Series(model.feature_importances_, index=feature_cols).sort_values(ascending=False)
    print("\nTop 20 Features (Gain):")
    print(importances.head(20))
    
    # Save top features
    out_path = Path(f"reports/features_top_lgbm_{args.timeframe}m.txt")
    with open(out_path, "w") as f:
        for feat in importances.head(20).index:
            f.write(f"{feat}\n")
    print(f"Results saved to {out_path}")

if __name__ == "__main__":
    main()
