# src/khms_trader/backtest/metrics.py

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import List
from khms_trader.backtest.hsms_single import Trade


def compute_total_return(equity_df: pd.DataFrame) -> float:
    """
    총 수익률 (단위: 0.25 → 25%)
    """
    start = float(equity_df["equity"].iloc[0])
    end = float(equity_df["equity"].iloc[-1])
    return (end - start) / start


def compute_max_drawdown(equity_df: pd.DataFrame) -> float:
    """
    최대 낙폭(MDD). (단위: -0.2 → -20%)
    """
    equity = equity_df["equity"].values.astype(float)
    running_max = np.maximum.accumulate(equity)
    drawdowns = equity / running_max - 1.0
    return float(drawdowns.min())


def compute_win_rate(trades: List[Trade]) -> float | None:
    """
    승률 (매도 거래 기준).
    트레이드가 하나도 없으면 None 반환.
    """
    sell_trades = [t for t in trades if t.side == "SELL"]
    if not sell_trades:
        return None

    wins = [t for t in sell_trades if t.pnl > 0]
    return len(wins) / len(sell_trades)
