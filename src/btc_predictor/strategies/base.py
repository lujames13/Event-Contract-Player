from abc import ABC, abstractmethod
import pandas as pd
from btc_predictor.models import PredictionSignal

class BaseStrategy(ABC):
    """所有預測策略的基類。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """策略唯一名稱，用於日誌和資料庫。"""
        pass

    @abstractmethod
    def predict(
        self,
        ohlcv: pd.DataFrame,
        timeframe_minutes: int,
    ) -> PredictionSignal:
        """
        輸入 OHLCV 數據，輸出預測信號。

        Args:
            ohlcv: 包含 open, high, low, close, volume 欄位的 DataFrame，
                   index 為 datetime (UTC)，按時間升序排列。
            timeframe_minutes: 預測的到期時間框架 (10 | 30 | 60 | 1440)。

        Returns:
            PredictionSignal，包含方向、信心度等資訊。
        """
        pass
