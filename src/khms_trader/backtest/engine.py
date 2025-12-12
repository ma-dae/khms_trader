from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any

import pandas as pd

from ..strategies.base import BaseStrategy


@dataclass
class BacktestResult:
    df: pd.DataFrame
    stats: Dict[str, Any]


def run_single_symbol_backtest(
    df: pd.DataFrame,
    strategy: BaseStrategy,
    *,
    risk_atr: float = 1.0,
) -> BacktestResult:
    """
    단일 종목 롱 온리 백테스트.

    매우 단순한 버전:
        - buy_signal True인 날 종가에 진입 (이미 포지션 없을 때만)
        - 보유 중:
            - ATR 기반 손절
            - 전략의 sell_signal 시 청산
    """
    sig = strategy.generate_signals(df)
    sig = sig.copy()

    sig["position"] = 0
    sig["entry_price"] = float("nan")
    sig["pnl"] = 0.0
    sig["equity"] = 0.0

    position = 0
    entry_price: Optional[float] = None
    equity = 0.0

    for i in range(1, len(sig)):
        row = sig.iloc[i]
        idx = sig.index[i]
        prev_equity = equity

        if position == 0:
            # 진입 조건
            if bool(row.get("buy_signal", False)):
                position = 1
                entry_price = float(row["close"])
                sig.at[idx, "position"] = 1
                sig.at[idx, "entry_price"] = entry_price
                equity = prev_equity
            else:
                equity = prev_equity
        else:
            # 보유 중
            price = float(row["close"])
            atr = float(row.get("atr", 0.0))
            stop_loss = entry_price - risk_atr * atr if entry_price is not None else None

            must_sell = False
            if stop_loss is not None and price <= stop_loss:
                must_sell = True
            if bool(row.get("sell_signal", False)):
                must_sell = True

            if must_sell:
                pnl = price - entry_price
                equity = prev_equity + pnl
                sig.at[idx, "pnl"] = pnl
                sig.at[idx, "position"] = 0
                sig.at[idx, "entry_price"] = float("nan")
                position = 0
                entry_price = None
            else:
                sig.at[idx, "position"] = 1
                sig.at[idx, "entry_price"] = entry_price
                # 미실현 손익을 equity에 반영 (단순형)
                equity = prev_equity + (price - entry_price)

        sig.at[idx, "equity"] = equity

    stats = {
        "final_equity": float(sig["equity"].iloc[-1]),
        "total_pnl": float(sig["pnl"].sum()),
        "num_trades": int((sig["pnl"] != 0).sum()),
    }

    return BacktestResult(df=sig, stats=stats)
