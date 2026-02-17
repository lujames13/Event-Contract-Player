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

    @property
    @abstractmethod
    def requires_fitting(self) -> bool:
        """策略是否需要訓練。"""
        pass

    @property
    def available_timeframes(self) -> list[int]:
        """回傳此策略已有訓練模型的 timeframe list。
        
        預設實作回傳空 list。有模型的策略應 override 此 property。
        """
        return []

    @abstractmethod
    def fit(
        self,
        ohlcv: pd.DataFrame,
        timeframe_minutes: int,
    ) -> None:
        """
        根據歷史數據訓練模型。
        
        Args:
            ohlcv: 包含 open, high, low, close, volume 欄位的 DataFrame，
                   index 為 datetime (UTC)，按時間升序排列。
            timeframe_minutes: 訓練目標的到期時間框架。
        """
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
