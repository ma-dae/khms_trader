# src/khms_trader/backtest/hsms_single.py

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd

from khms_trader.strategies.hsms import HSMSStrategy, HSMSConfig


@dataclass
class Trade:
    date: pd.Timestamp
    side: str      # "BUY" or "SELL"
    price: float
    qty: int
    pnl: float = 0.0


class HSMSSingleBacktester:
    """
    단일 종목 HSMS 백테스터.

    단순 규칙:
      - buy_signal == True 이고 포지션 없으면 → 전액 매수
      - sell_signal == True 이고 포지션 있으면 → 전량 매도
      - 체결가는 모두 종가(close) 기준
    """

    def __init__(
        self,
        symbol: str,
        initial_cash: int = 10_000_000,
        strategy: HSMSStrategy | None = None,
    ) -> None:
        self.symbol = symbol
        self.initial_cash = initial_cash
        self.strategy = strategy or HSMSStrategy()

        self.cash = initial_cash
        self.position_qty = 0
        self.position_entry_price = 0.0

        self.trades: List[Trade] = []
        self.equity_curve: List[dict] = []

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        df: raw/{symbol}.csv 에서 로딩한 시계열
            (date, open, high, low, close, volume, foreign_net_buy, ...)

        반환:
          equity_df: 일자별 자산 상태 (date, close, cash, position_qty, equity)
        """

        # 1) 전략 시그널 계산
        df = df.copy()
        df = self.strategy.generate_signals(df)
        df = df.sort_values("date").reset_index(drop=True)

        for _, row in df.iterrows():
            date = row["date"]
            close = float(row["close"])
            buy_signal = bool(row["buy_signal"])
            sell_signal = bool(row["sell_signal"])

            # 2) 매수 로직: 포지션 없을 때만
            if buy_signal and self.position_qty == 0:
                qty = int(self.cash // close)
                if qty > 0:
                    self.cash -= qty * close
                    self.position_qty = qty
                    self.position_entry_price = close
                    self.trades.append(Trade(date, "BUY", close, qty))

            # 3) 매도 로직: 포지션 있을 때만
            elif sell_signal and self.position_qty > 0:
                qty = self.position_qty
                self.cash += qty * close
                pnl = (close - self.position_entry_price) * qty
                self.trades.append(Trade(date, "SELL", close, qty, pnl))
                self.position_qty = 0
                self.position_entry_price = 0.0

            # 4) 일별 평가금액 기록
            equity = self.cash + self.position_qty * close
            self.equity_curve.append(
                {
                    "date": date,
                    "close": close,
                    "cash": self.cash,
                    "position_qty": self.position_qty,
                    "equity": equity,
                }
            )

        return pd.DataFrame(self.equity_curve)

    def get_trades(self) -> List[Trade]:
        return self.trades
