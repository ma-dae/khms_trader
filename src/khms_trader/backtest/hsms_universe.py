# src/khms_trader/backtest/hsms_universe.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List

import pandas as pd

from khms_trader.backtest.dataset_loader import load_universe, load_raw
from khms_trader.backtest.hsms_single import HSMSSingleBacktester
from khms_trader.backtest.metrics import (
    compute_total_return,
    compute_max_drawdown,
    compute_win_rate,
)
from khms_trader.strategies.hsms import HSMSStrategy, HSMSConfig


@dataclass
class SymbolResult:
    symbol: str
    name: str
    total_return: float
    mdd: float
    win_rate: Optional[float]
    final_equity: float
    n_trades: int


class HSMSUniverseBacktester:
    """
    특정 유니버스 날짜(kosdaq_YYYYMMDD.csv)에 포함된
    각 종목에 대해 HSMS 단일 종목 백테스트를 수행하고,
    성과 지표를 집계하는 클래스.
    """

    def __init__(
        self,
        universe_date: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        initial_cash: int = 10_000_000,
        config: Optional[HSMSConfig] = None,
    ) -> None:
        """
        universe_date: 'YYYYMMDD' (예: '20251201')
        start_date, end_date: 백테스트 구간 (없으면 전체 데이터 사용)
        """
        self.universe_date = universe_date
        self.start_date = pd.to_datetime(start_date) if start_date else None
        self.end_date = pd.to_datetime(end_date) if end_date else None
        self.initial_cash = initial_cash
        self.config = config or HSMSConfig()

    def run(self) -> pd.DataFrame:
        """
        반환:
          - 종목별 성과 지표를 담은 DataFrame
            columns: [symbol, name, total_return, mdd, win_rate, final_equity, n_trades]
        """

        uni = load_universe(self.universe_date)
        if "ticker" not in uni.columns:
            raise KeyError("universe 파일에 'ticker' 컬럼이 없습니다.")
        if "name" not in uni.columns:
            # name 컬럼이 없으면 심볼을 이름으로 사용
            uni["name"] = uni["ticker"].astype(str)

        results: List[SymbolResult] = []

        for _, row in uni.iterrows():
            symbol = str(row["ticker"])
            name = str(row.get("name", symbol))

            print(f"[HSMSUniverseBacktester] {symbol} ({name}) 백테스트 시작...")

            # 1) raw 데이터 로딩
            try:
                df = load_raw(symbol)
            except FileNotFoundError:
                print(f"[HSMSUniverseBacktester] {symbol}: raw 데이터 없음 -> 스킵")
                continue
            except Exception as e:
                print(f"[HSMSUniverseBacktester] {symbol}: 로딩 오류 -> {e}")
                continue

            # 2) 날짜 필터링 (옵션)
            if self.start_date is not None:
                df = df[df["date"] >= self.start_date]
            if self.end_date is not None:
                df = df[df["date"] <= self.end_date]

            if len(df) < 20:
                # 데이터가 너무 적으면 전략 성능 의미가 약하니 스킵 (임의 기준)
                print(f"[HSMSUniverseBacktester] {symbol}: 데이터 부족 ({len(df)} rows) -> 스킵")
                continue

            # 3) 전략 & 백테스터 준비
            strategy = HSMSStrategy(self.config)
            bt = HSMSSingleBacktester(
                symbol=symbol,
                initial_cash=self.initial_cash,
                strategy=strategy,
            )

            try:
                equity_df = bt.run(df)
                trades = bt.get_trades()
            except Exception as e:
                print(f"[HSMSUniverseBacktester] {symbol}: 백테스트 중 오류 -> {e}")
                continue

            if equity_df.empty:
                print(f"[HSMSUniverseBacktester] {symbol}: equity_df 비어있음 -> 스킵")
                continue

            # 4) 성과 지표 계산
            total_ret = compute_total_return(equity_df)
            mdd = compute_max_drawdown(equity_df)
            win_rate = compute_win_rate(trades)
            final_equity = float(equity_df["equity"].iloc[-1])
            n_trades = len([t for t in trades if t.side == "SELL"])

            results.append(
                SymbolResult(
                    symbol=symbol,
                    name=name,
                    total_return=total_ret,
                    mdd=mdd,
                    win_rate=win_rate,
                    final_equity=final_equity,
                    n_trades=n_trades,
                )
            )

        # List[SymbolResult] → DataFrame
        if not results:
            return pd.DataFrame(
                columns=[
                    "symbol",
                    "name",
                    "total_return",
                    "mdd",
                    "win_rate",
                    "final_equity",
                    "n_trades",
                ]
            )

        df_res = pd.DataFrame([r.__dict__ for r in results])
        return df_res
