# src/khms_trader/backtest/hsms_single.py

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any

import pandas as pd

from khms_trader.config import load_settings
from khms_trader.strategies.hsms import HSMSStrategy
from khms_trader.backtest.configs import BacktestConfig


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

    규칙(단순):
      - buy_signal == True 이고 포지션 없으면 → 가능한 한 전액 매수
      - sell_signal == True 이고 포지션 있으면 → 전량 매도

    체결가:
      - fill_mode="close": 신호 발생 당일 종가 체결(비교용)
      - fill_mode="next_open": 신호 발생 다음날 시가 체결(룩어헤드 방지 기본)

    비용:
      - 수수료: 매수/매도 모두 적용
      - 거래세: 매도에만 적용
      - 슬리피지: 매수는 +, 매도는 - 방향으로 체결가에 반영
    """

    def __init__(
        self,
        symbol: str,
        initial_cash: int = 10_000_000,
        strategy: Optional[HSMSStrategy] = None,
        bt_config: Optional[BacktestConfig] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> None:
        settings = settings or load_settings()
        trading_cfg = settings.get("trading") or {}

        self.symbol = symbol
        self.initial_cash = int(initial_cash)
        self.strategy = strategy or HSMSStrategy()
        self.bt_config = bt_config or BacktestConfig(**trading_cfg)

        self.cash: float = float(self.initial_cash)
        self.position_qty: int = 0
        self.position_entry_price: float = 0.0

        self.trades: List[Trade] = []
        self.equity_curve: List[dict] = []

    def _get_exec_price(self, df: pd.DataFrame, i: int) -> Optional[float]:
        """
        체결가 결정:
        - close: 당일 종가
        - next_open: 다음날 시가 (마지막 날은 체결 불가 -> None)
        """
        c = self.bt_config

        if c.fill_mode == "close":
            return float(df.iloc[i]["close"])

        if c.fill_mode == "next_open":
            if i + 1 >= len(df):
                return None
            return float(df.iloc[i + 1]["open"])

        # 알 수 없는 fill_mode면 close로 fallback
        return float(df.iloc[i]["close"])

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        df: raw/{symbol}.csv에서 로딩한 시계열
            (date, open, high, low, close, volume, foreign_net_buy, ...)

        반환:
          equity_df: 일자별 자산 상태 (date, close, cash, position_qty, equity)
        """

        # 0) 기본 정리
        df = df.copy()
        df = df.sort_values("date").reset_index(drop=True)
  

        # 1) 전략 시그널 계산
        df = self.strategy.generate_signals(df)

        c = self.bt_config
        fee = c.fee_rate
        tax = c.tax_rate
        slip = c.slippage_rate
        
        if "vol_ma" not in df.columns:
            df["vol_ma"] = df["volume"].rolling(20).mean()

        if "ret_abs_ma" not in df.columns:
            df["ret_abs_ma"] = df["close"].pct_change().abs().rolling(20).mean()


        for i in range(len(df)):
            row = df.iloc[i]
            date = row["date"]
            close = float(row["close"])
            buy_signal = bool(row.get("buy_signal", False))
            sell_signal = bool(row.get("sell_signal", False))

            if row.get("regime") == "Sideways" and buy_signal:
                vol = float(row.get("volume", 0.0) or 0.0)
                vol_ma = float(row.get("vol_ma", 0.0) or 0.0)
                vol_ok = (vol_ma > 0) and ((vol / vol_ma) >= 1.3)

                volat = float(row.get("ret_abs_ma", 0.0) or 0.0)
                volat_ok = volat >= 0.012

                buy_signal = bool(vol_ok and volat_ok)



            exec_price = self._get_exec_price(df, i)

            # next_open인데 마지막 날이면 체결 불가 -> 신호 무시하고 평가만 기록
            if exec_price is None:
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
                continue

            # 슬리피지 적용 (체결가에 반영)
            buy_price = exec_price * (1.0 + slip)
            sell_price = exec_price * (1.0 - slip)

            # 2) 매수: 포지션 없을 때만
            if buy_signal and self.position_qty == 0:
                # 수수료까지 포함해 살 수 있는 수량
                qty = int(self.cash // (buy_price * (1.0 + fee)))

                if qty > 0:
                    notional = qty * buy_price
                    cost = notional * (1.0 + fee)  # 매수 수수료 포함
                    # 현금 부족 방어(정수 나눗셈이라 거의 필요 없지만 안전)
                    if cost <= self.cash + 1e-9:
                        self.cash -= cost
                        self.position_qty = qty
                        self.position_entry_price = buy_price
                        self.trades.append(Trade(date, "BUY", buy_price, qty))

            # 3) 매도: 포지션 있을 때만
            elif sell_signal and self.position_qty > 0:
                qty = self.position_qty
                notional = qty * sell_price
                proceeds = notional * (1.0 - fee - tax)  # 매도 수수료+거래세 차감
                self.cash += proceeds                     # ✅ 매도는 현금 증가

                pnl = (sell_price - self.position_entry_price) * qty
                self.trades.append(Trade(date, "SELL", sell_price, qty, pnl))

                self.position_qty = 0
                self.position_entry_price = 0.0

            # 4) 일별 평가금액 기록(평가는 항상 당일 종가로 마크)
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
