import pandas as pd
import numpy as np
import argparse
import sys
from pathlib import Path
from boruta import BorutaPy
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier

# Setup path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from btc_predictor.data.store import DataStore
from btc_predictor.strategies.xgboost_v1.features import generate_features, get_feature_columns
from btc_predictor.data.labeling import add_direction_labels

def main():
    parser = argparse.ArgumentParser(description="Feature Selection using Boruta")
    parser.add_argument("--timeframe", type=int, default=10, help="Timeframe (10, 30, 60, 1440)")
    parser.add_argument("--days", type=int, default=180, help="Days of data to analyze")
    parser.add_argument("--model", type=str, default="xgboost", choices=["xgboost", "lgbm"], help="Model to use for Boruta")
    
    args = parser.parse_args()
    
    store = DataStore()
    limit = args.days * 24 * 60
    df = store.get_ohlcv("BTCUSDT", "1m", limit=limit)
    
    if df.empty:
        print("No data found")
        return

    print(f"Generating features for {len(df)} rows...")
    feat_df = generate_features(df)
    labeled_df = add_direction_labels(feat_df, args.timeframe)
    
    feature_cols = get_feature_columns()
    labeled_df = labeled_df.dropna(subset=["label"] + feature_cols)
    
    X = labeled_df[feature_cols].values
    y = labeled_df["label"].values
    
    print(f"Starting Boruta with {args.model} on {len(labeled_df)} samples and {len(feature_cols)} features...")
    
    if args.model == "xgboost":
        model = XGBClassifier(n_jobs=-1, max_depth=5)
    else:
        model = LGBMClassifier(n_jobs=-1, max_depth=5, verbose=-1)
        
    feat_selector = BorutaPy(model, n_estimators='auto', verbose=2, random_state=42, max_iter=50)
    feat_selector.fit(X, y)
    
    # Results
    selected_features = [feature_cols[i] for i, selected in enumerate(feat_selector.support_) if selected]
    weak_features = [feature_cols[i] for i, weak in enumerate(feat_selector.support_weak_) if weak]
    
    print("\n" + "="*30)
    print("BORUTA RESULTS")
    print("="*30)
    print(f"Selected ({len(selected_features)}): {selected_features}")
    print(f"Weak ({len(weak_features)}): {weak_features}")
    print("="*30)
    
    # Save to a file for reference
    out_path = Path(f"reports/features_boruta_{args.model}_{args.timeframe}m.txt")
    with open(out_path, "w") as f:
        f.write(f"Selected: {selected_features}\n")
        f.write(f"Weak: {weak_features}\n")
    print(f"Results saved to {out_path}")

if __name__ == "__main__":
    main()
