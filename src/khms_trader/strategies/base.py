from __future__ import annotations

from abc import ABC, abstractmethod
import pandas as pd

class BaseStrategy(ABC):

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        입력 df: 최소 ['date','close','volume']를 가진 시계열 데이터
        출력 df: 원본 df + 전략이 계산한 시그널 컬럼
                 (예: 'buy_signal', 'sell_signal', 지표 컬럼 등)
        """
        pass

