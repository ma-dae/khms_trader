from __future__ import annotations

import pandas as pd

from .base import BaseStrategy
from ..data.features import add_hsms_features


class HSMSStrategy(BaseStrategy):
    """
    K-HSMS (Korea Hybrid Swing Momentum Strategy) 구현 클래스.
    """

    name = "k-hsms"

    def __init__(
        self,
        *,
        rsi_period: int = 14,
        atr_period: int = 14,
        vol_window: int = 20,
        foreign_window: int = 3,
    ) -> None:
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.vol_window = vol_window
        self.foreign_window = foreign_window

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        입력 df에 HSMS 지표와 매수/매도 시그널을 추가해 반환한다.

        요구 컬럼:
            - 'close', 'high', 'low', 'volume', 'foreign_net_buy'
        """
        out = add_hsms_features(
            df,
            rsi_period=self.rsi_period,
            atr_period=self.atr_period,
            vol_window=self.vol_window,
            foreign_window=self.foreign_window,
        )

        # 매수 신호: 추세 + RSI 50 재돌파 + 거래량 증가 + 외국인 수급
        buy_cond = (
            out["trend_ok"]
            & out["rsi_cross_50"]
            & out["vol_ok"]
            & out["foreign_trend_ok"]
        )
        out["buy_signal"] = buy_cond

        # 매도 신호: 1차 버전은 ema50 이탈 시 매도
        # (추후 ATR 트레일링 스탑으로 보완 예정)
        out["sell_signal"] = out["close"] < out["ema50"]

        return out
