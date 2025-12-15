from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .base import BaseStrategy


@dataclass
class HSMSConfig:
    """
    단순화된 HSMS 전략 설정값 모음.

    - ma_window: 추세 기준이 되는 이동평균 기간
    - momentum_window: 모멘텀 계산 기간
    - volume_lookback: 거래량 평균을 보는 기간
    - volume_multiplier: 평균 거래량 대비 몇 배 이상일 때만 진입을 허용할지
    """

    ma_window: int = 20
    momentum_window: int = 5
    volume_lookback: int = 20
    volume_multiplier: float = 1.1


class HSMSStrategy(BaseStrategy):
    """
    단순화 버전 HSMS 전략.

    아이디어:
      - 종가가 MA(20) 위에 있고
      - 5일 모멘텀이 플러스이며
      - 거래량이 최근 20일 평균의 1.1배 이상이면 -> 매수 신호

      - 종가가 MA(20) 아래로 1% 이상 이탈하거나
      - 5일 모멘텀이 마이너스로 전환되면 -> 매도 신호
    """

    def __init__(self, config: HSMSConfig | None = None) -> None:
        self.config = config or HSMSConfig()

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        입력:
          - df: 최소한 ['close', 'volume'] 컬럼이 있는 일봉 데이터
                (이미 loader에서 컬럼명 통일했다고 가정)

        출력:
          - df_with_signals: 원본 df에
              ['ma', 'momentum', 'vol_avg', 'buy_signal', 'sell_signal']
            컬럼이 추가된 DataFrame
        """

        if df.empty:
            return df.copy()

        # 원본 손상 방지
        df = df.copy()

        c = self.config

        # 1) 추세: MA(20)
        df["ma"] = df["close"].rolling(c.ma_window).mean()

        # 2) 모멘텀: 5일 전 대비 가격 차이
        df["momentum"] = df["close"] - df["close"].shift(c.momentum_window)

        # 3) 거래량 기준: 최근 20일 평균
        df["vol_avg"] = df["volume"].rolling(c.volume_lookback).mean()

        # 4) 매수 신호 조건
        buy_cond = (
            (df["close"] > df["ma"])  # 추세 상방
            & (df["momentum"] > 0)    # 모멘텀 플러스
            & (df["volume"] > df["vol_avg"] * c.volume_multiplier)  # 거래량 증가
        )

        # 5) 매도 신호 조건
        sell_cond = (
            (df["close"] < df["ma"] * 0.99)  # 추세 이탈(1% 이상)
            | (df["momentum"] < 0)           # 모멘텀 마이너스
        )

        # NaN → False 처리
        df["buy_signal"] = buy_cond.fillna(False)
        df["sell_signal"] = sell_cond.fillna(False)

        return df

# ==============================
# HSMS 2.0 (외국인 수급 필터 추가)
# ==============================

@dataclass
class HSMS2Config(HSMSConfig):
    """
    HSMS 2.0 설정
    - foreign_lookback: 외국인 순매수 합산 기간
    - foreign_min_sum: 이 값 이상일 때만 매수 허용
    """
    foreign_lookback: int = 5
    foreign_min_sum: float = 0.0


class HSMS2Strategy(BaseStrategy):
    """
    HSMS 2.0 전략

    HSMS 1.0 조건 +
    - 최근 N일 외국인 순매수 합 > foreign_min_sum 일 때만 매수
    - 외국인 순매수 합 < 0 이면 매도 신호
    """

    def __init__(self, config: HSMS2Config | None = None) -> None:
        self.config = config or HSMS2Config()

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df.copy()

        df = df.copy()
        c = self.config

        # 1) 기본 HSMS 1.0 지표
        df["ma"] = df["close"].rolling(c.ma_window).mean()
        df["momentum"] = df["close"] - df["close"].shift(c.momentum_window)
        df["vol_avg"] = df["volume"].rolling(c.volume_lookback).mean()

        # 2) 외국인 순매수 롤링 합
        if "foreign_net_buy" not in df.columns:
            df["foreign_net_buy"] = 0.0

        df["foreign_sum"] = (
            df["foreign_net_buy"]
            .rolling(c.foreign_lookback)
            .sum()
        )

        # 3) 매수 조건
        buy_cond = (
            (df["close"] > df["ma"]) &
            (df["momentum"] > 0) &
            (df["volume"] > df["vol_avg"] * c.volume_multiplier) &
            (df["foreign_sum"] > c.foreign_min_sum)
        )

        # 4) 매도 조건
        sell_cond = (
            (df["close"] < df["ma"] * 0.99) |
            (df["momentum"] < 0) |
            (df["foreign_sum"] < 0)
        )

        df["buy_signal"] = buy_cond.fillna(False)
        df["sell_signal"] = sell_cond.fillna(False)

        return df
