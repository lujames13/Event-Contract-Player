import optuna
import pandas as pd
import numpy as np
import lightgbm as lgb
from datetime import datetime, timedelta
from pathlib import Path
import sys
import argparse
import pickle

# Add src to sys.path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from btc_predictor.data.store import DataStore
from btc_predictor.data.labeling import add_direction_labels
from btc_predictor.strategies.lgbm_v1_tuned.features import generate_features, get_feature_columns
from btc_predictor.utils.config import load_constants

def objective(trial, labeled_df, feature_cols, timeframe_minutes, threshold):
    params = {
        "num_leaves": trial.suggest_int("num_leaves", 15, 127),
        "min_child_samples": trial.suggest_int("min_child_samples", 10, 100),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "subsample": trial.suggest_float("subsample", 0.5, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.3, 1.0),
        "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
        "objective": "binary",
        "verbose": -1,
        "n_jobs": -1
    }
    early_stopping_rounds = trial.suggest_int("early_stopping_rounds", 50, 150)
    
    seeds = [42, 123]
    seed_das = []
    
    # Fast Walk-Forward
    train_days = 180
    test_days = 7
    
    all_times = labeled_df.index
    # Use only last 120 days for fast tuning
    end_time = all_times[-1]
    tuning_start_time = end_time - timedelta(days=120)
    
    # To speed up, we pre-calculate folds
    folds = []
    curr = tuning_start_time
    while curr < end_time:
        fold_end = curr + timedelta(days=test_days)
        train_start = curr - timedelta(days=train_days)
        
        train_data = labeled_df[(labeled_df.index >= train_start) & (labeled_df.index < curr)]
        test_data = labeled_df[(labeled_df.index >= curr) & (labeled_df.index < fold_end)]
        
        # Sample test data at timeframe intervals to match engine.py
        test_data = test_data.iloc[::timeframe_minutes]
        
        if len(train_data) > 100 and not test_data.empty:
            folds.append((train_data, test_data))
            
        curr += timedelta(days=test_days)

    if not folds:
        return 0.0

    for seed in seeds:
        params['random_state'] = seed
        params['n_jobs'] = 1 # One job per model fit to allow Optuna many jobs
        total_wins = 0
        total_trades = 0
        
        for train_df, test_df in folds:
            # Drop NaN for training
            train_clean = train_df.dropna(subset=['label'] + feature_cols)
            if len(train_clean) < 100: continue
            
            # Val split (20%)
            val_size = int(len(train_clean) * 0.2)
            X_train = train_clean[feature_cols].iloc[:-val_size]
            y_train = train_clean['label'].iloc[:-val_size]
            X_val = train_clean[feature_cols].iloc[-val_size:]
            y_val = train_clean['label'].iloc[-val_size:]
            
            model = lgb.LGBMClassifier(**params)
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                callbacks=[lgb.early_stopping(stopping_rounds=early_stopping_rounds)]
            )
            
            # Predict
            test_clean = test_df.dropna(subset=['label'])
            if not test_clean.empty:
                X_test = test_clean[feature_cols]
                y_test = test_clean['label']
                
                probs = model.predict_proba(X_test)[:, 1]
                confidences = np.where(probs > 0.5, probs, 1.0 - probs)
                traded_mask = confidences >= threshold
                
                if traded_mask.any():
                    preds = (probs[traded_mask] > 0.5).astype(int)
                    wins = (preds == y_test[traded_mask].values).sum()
                    total_wins += wins
                    total_trades += len(preds)
        
        da = total_wins / total_trades if total_trades > 0 else 0.5
        seed_das.append(da)
        
    return np.mean(seed_das)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=40)
    parser.add_argument("--timeframe", type=int, default=30)
    args = parser.parse_args()

    print(f"Loading data for tuning (Timeframe: {args.timeframe}m, Trials: {args.trials})...")
    store = DataStore()
    # Loading enough data for 120 days tuning window
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=120 + 180 + 30) # buffer
    
    df = store.get_ohlcv("BTCUSDT", "1m", 
                         start_time=int(start_dt.timestamp() * 1000),
                         end_time=int(end_dt.timestamp() * 1000))
    
    if df.empty:
        print("No data found!")
        return

    print("Generating features and labels...")
    feat_df = generate_features(df)
    labeled_df = add_direction_labels(feat_df, args.timeframe)
    feature_cols = get_feature_columns()
    
    constants = load_constants()
    threshold = constants.get("confidence_thresholds", {}).get(args.timeframe, 0.591)
    
    print(f"Starting optuna study for threshold {threshold}...")
    
    study = optuna.create_study(direction="maximize")
    # Parallelizing trials might be tricky with SQLite/In-memory but let's try n_jobs=2
    study.optimize(lambda trial: objective(trial, labeled_df, feature_cols, args.timeframe, threshold), 
                   n_trials=args.trials, n_jobs=2)
    
    print("Optimization finished.")
    print(f"Best trial DA: {study.best_value}")
    print("Best params:", study.best_params)
    
    # Save best params
    save_path = Path("src/btc_predictor/strategies/lgbm_v1_tuned/best_params.pkl")
    with open(save_path, "wb") as f:
        pickle.dump(study.best_params, f)
    print(f"Best params saved to {save_path}")

if __name__ == "__main__":
    main()
