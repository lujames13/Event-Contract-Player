# Models Directory

此目錄存放訓練好的機器學習模型。

## 模型檔案

- `xgboost_10m.pkl`: 10 分鐘方向預測模型
- `xgboost_30m.pkl`: 30 分鐘方向預測模型  
- `xgboost_60m.pkl`: 60 分鐘方向預測模型

## 訓練模型

```bash
python scripts/train_xgboost_model.py
```

## 注意事項

- 模型檔案較大，已加入 `.gitignore` 不會 commit 到 Git
- 每次 clone 專案後需重新訓練模型
- 建議定期重新訓練以適應市場變化
