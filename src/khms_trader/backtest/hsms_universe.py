# src/khms_trader/backtest/hsms_universe.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Type, Any, Dict

import pandas as pd

from khms_trader.backtest.dataset_loader import load_universe, load_raw
from khms_trader.backtest.hsms_single import HSMSSingleBacktester
from khms_trader.backtest.metrics import (
    compute_total_return,
    compute_max_drawdown,
    compute_win_rate,
)
from khms_trader.backtest.configs import BacktestConfig
from khms_trader.backtest.bt_config_factory import make_bt_config
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
    status: str = "OK"          # OK / SKIP / ERROR
    reason: str = ""            # 스킵/에러 사유(디버깅용)


class HSMSUniverseBacktester:
    """
    특정 유니버스 날짜(kosdaq_YYYYMMDD.csv)에 포함된
    각 종목에 대해 HSMS 단일 종목 백테스트를 수행하고,
    성과 지표를 집계하는 클래스.

    리팩터링 포인트:
    - bt_config(비용/체결 가정)를 외부에서 주입 가능하도록 해서
      scripts/test_hsms.py, regime_analysis_universe.py와 동일한 가정을 강제한다.
    """

    def __init__(
        self,
        universe_date: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        initial_cash: int = 10_000_000,
        strategy_cls: Type[Any] = HSMSStrategy,
        strategy_config: Optional[Any] = None,
        bt_config: Optional[BacktestConfig] = None,
        min_rows: int = 20,
        verbose: bool = True,
    ) -> None:
        self.universe_date = universe_date
        self.start_date = pd.to_datetime(start_date) if start_date else None
        self.end_date = pd.to_datetime(end_date) if end_date else None
        self.initial_cash = initial_cash

        self.strategy_cls = strategy_cls
        self.strategy_config = strategy_config or HSMSConfig()

        # ✅ 비용/체결 가정 단일화: 주입 없으면 setting.yaml 기반으로 생성
        self.bt_config = bt_config or make_bt_config()

        self.min_rows = int(min_rows)
        self.verbose = bool(verbose)

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)

    def _date_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.start_date is not None:
            df = df[df["date"] >= self.start_date]
        if self.end_date is not None:
            df = df[df["date"] <= self.end_date]
        return df

    def run(self) -> pd.DataFrame:
        """
        반환:
          - 종목별 성과 지표를 담은 DataFrame
            columns:
              [symbol, name, total_return, mdd, win_rate, final_equity, n_trades, status, reason]
        """

        uni = load_universe(self.universe_date)

        if "ticker" not in uni.columns:
            raise KeyError("universe 파일에 'ticker' 컬럼이 없습니다.")

        if "name" not in uni.columns:
            uni["name"] = uni["ticker"].astype(str)

        results: List[SymbolResult] = []

        for _, row in uni.iterrows():
            symbol = str(row["ticker"])
            name = str(row.get("name", symbol))

            self._log(f"[HSMSUniverseBacktester] {symbol} ({name}) backtest...")

            # 1) raw 데이터 로딩
            try:
                df = load_raw(symbol)
            except FileNotFoundError:
                results.append(
                    SymbolResult(
                        symbol=symbol,
                        name=name,
                        total_return=0.0,
                        mdd=0.0,
                        win_rate=None,
                        final_equity=float(self.initial_cash),
                        n_trades=0,
                        status="SKIP",
                        reason="raw_not_found",
                    )
                )
                self._log(f"  - SKIP: raw 데이터 없음")
                continue
            except Exception as e:
                results.append(
                    SymbolResult(
                        symbol=symbol,
                        name=name,
                        total_return=0.0,
                        mdd=0.0,
                        win_rate=None,
                        final_equity=float(self.initial_cash),
                        n_trades=0,
                        status="ERROR",
                        reason=f"load_error:{e}",
                    )
                )
                self._log(f"  - ERROR: 로딩 오류 -> {e}")
                continue

            # 2) 날짜 필터링 (옵션)
            try:
                df = self._date_filter(df)
            except Exception as e:
                results.append(
                    SymbolResult(
                        symbol=symbol,
                        name=name,
                        total_return=0.0,
                        mdd=0.0,
                        win_rate=None,
                        final_equity=float(self.initial_cash),
                        n_trades=0,
                        status="ERROR",
                        reason=f"date_filter_error:{e}",
                    )
                )
                self._log(f"  - ERROR: 날짜 필터 오류 -> {e}")
                continue

            if df is None or df.empty or len(df) < self.min_rows:
                results.append(
                    SymbolResult(
                        symbol=symbol,
                        name=name,
                        total_return=0.0,
                        mdd=0.0,
                        win_rate=None,
                        final_equity=float(self.initial_cash),
                        n_trades=0,
                        status="SKIP",
                        reason=f"insufficient_rows:{0 if df is None else len(df)}",
                    )
                )
                self._log(f"  - SKIP: 데이터 부족 ({0 if df is None else len(df)} rows)")
                continue

            # 3) 전략 & 백테스터 준비 (bt_config를 명시적으로 주입)
            try:
                strategy = self.strategy_cls(self.strategy_config)
            except Exception as e:
                results.append(
                    SymbolResult(
                        symbol=symbol,
                        name=name,
                        total_return=0.0,
                        mdd=0.0,
                        win_rate=None,
                        final_equity=float(self.initial_cash),
                        n_trades=0,
                        status="ERROR",
                        reason=f"strategy_init_error:{e}",
                    )
                )
                self._log(f"  - ERROR: 전략 생성 오류 -> {e}")
                continue

            bt = HSMSSingleBacktester(
                symbol=symbol,
                initial_cash=self.initial_cash,
                strategy=strategy,
                bt_config=self.bt_config,  # ✅ 통일된 비용/체결 가정
            )

            # 4) 백테스트 실행
            try:
                equity_df = bt.run(df)
                trades = bt.get_trades()
            except Exception as e:
                results.append(
                    SymbolResult(
                        symbol=symbol,
                        name=name,
                        total_return=0.0,
                        mdd=0.0,
                        win_rate=None,
                        final_equity=float(self.initial_cash),
                        n_trades=0,
                        status="ERROR",
                        reason=f"backtest_error:{e}",
                    )
                )
                self._log(f"  - ERROR: 백테스트 실행 오류 -> {e}")
                continue

            if equity_df is None or equity_df.empty:
                results.append(
                    SymbolResult(
                        symbol=symbol,
                        name=name,
                        total_return=0.0,
                        mdd=0.0,
                        win_rate=None,
                        final_equity=float(self.initial_cash),
                        n_trades=0,
                        status="SKIP",
                        reason="empty_equity_df",
                    )
                )
                self._log(f"  - SKIP: equity_df 비어있음")
                continue

            # 5) 성과 지표 계산
            try:
                total_ret = float(compute_total_return(equity_df))
                mdd = float(compute_max_drawdown(equity_df))
                win_rate = compute_win_rate(trades)
                final_equity = float(equity_df["equity"].iloc[-1])
                n_trades = len([t for t in trades if getattr(t, "side", None) == "SELL"])
            except Exception as e:
                results.append(
                    SymbolResult(
                        symbol=symbol,
                        name=name,
                        total_return=0.0,
                        mdd=0.0,
                        win_rate=None,
                        final_equity=float(self.initial_cash),
                        n_trades=0,
                        status="ERROR",
                        reason=f"metrics_error:{e}",
                    )
                )
                self._log(f"  - ERROR: 지표 계산 오류 -> {e}")
                continue

            results.append(
                SymbolResult(
                    symbol=symbol,
                    name=name,
                    total_return=total_ret,
                    mdd=mdd,
                    win_rate=win_rate,
                    final_equity=final_equity,
                    n_trades=n_trades,
                    status="OK",
                    reason="",
                )
            )

        # 6) 결과 DataFrame 반환
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
                    "status",
                    "reason",
                ]
            )

        df_res = pd.DataFrame([r.__dict__ for r in results])
        # 보기 편하게 정렬(OK 먼저, return 큰 순)
        if "status" in df_res.columns:
            df_res["status_rank"] = df_res["status"].map({"OK": 0, "SKIP": 1, "ERROR": 2}).fillna(9)
            df_res = df_res.sort_values(["status_rank", "total_return"], ascending=[True, False]).drop(columns=["status_rank"])

        return df_res
