from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class BaseStrategy(ABC):
    """
    전략 공통 인터페이스.

    단일 종목의 시계열 DataFrame을 입력으로 받아
    매수/매도 시그널이 포함된 DataFrame을 반환한다.
    """

    name: str = "base"

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        전략 시그널 생성.

        df: OHLCV 및 필요한 파생 컬럼이 담긴 DataFrame
        반환: 'buy_signal', 'sell_signal' 등의 컬럼이 추가된 DataFrame
        """
        raise NotImplementedError
