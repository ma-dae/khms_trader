import argparse
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import traceback

from khms_trader.config import load_settings
from khms_trader.data.screener import screen_top_by_volume_volatility
from khms_trader.data.loader import load_symbol_ohlcv_with_foreign

from khms_trader.backtest.hsms_single import HSMSSingleBacktester
from khms_trader.backtest.configs import BacktestConfig
from khms_trader.backtest.metrics import compute_total_return, compute_max_drawdown, compute_win_rate
from khms_trader.strategies.hsms import HSMSStrategy, HSMSConfig
from khms_trader.backtest.bt_config_factory import make_bt_config

print("=== regime_analysis_universe.py VERSION 2025-12-15 A ===")


def _ensure_date_index(df: pd.DataFrame) -> pd.DataFrame:
    """loader 결과가 index=date이거나 date 컬럼이 없을 수 있어 통일."""
    out = df.copy()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"])
        out = out.sort_values("date")
        out = out.set_index("date")
        return out
    # index가 날짜라고 가정
    out.index = pd.to_datetime(out.index)
    out = out.sort_index()
    return out


def build_regime_table(
    benchmark_symbol: str,
    ma_window: int = 200,
    slope_days: int = 20,
    use_processed: bool = True,
) -> pd.DataFrame:
    """
    레짐 라벨 생성:
    - Bull: close > MA and MA slope > 0
    - Bear: close < MA and MA slope < 0
    - Sideways: otherwise
    """
    bm = load_symbol_ohlcv_with_foreign(benchmark_symbol, use_processed=use_processed)
    bm = _ensure_date_index(bm)

    if "close" not in bm.columns:
        raise KeyError(f"benchmark df missing 'close'. columns={list(bm.columns)}")

    bm["ma"] = bm["close"].rolling(ma_window).mean()
    bm["ma_slope"] = bm["ma"].diff(slope_days)

    def _label(row) -> str:
        if pd.isna(row["ma"]) or pd.isna(row["ma_slope"]):
            return "Unknown"
        if row["close"] > row["ma"] and row["ma_slope"] > 0:
            return "Bull"
        if row["close"] < row["ma"] and row["ma_slope"] < 0:
            return "Bear"
        return "Sideways"

    bm["regime"] = bm.apply(_label, axis=1)
    return bm[["regime", "close", "ma", "ma_slope"]].copy()


def _get_equity_series(equity_df: pd.DataFrame) -> pd.Series:
    for col in ["equity", "portfolio", "portfolio_value", "value", "total_value"]:
        if col in equity_df.columns:
            return equity_df[col].astype(float)
    num_cols = [c for c in equity_df.columns if pd.api.types.is_numeric_dtype(equity_df[c])]
    if not num_cols:
        raise KeyError(f"equity_df has no numeric column. columns={list(equity_df.columns)}")
    return equity_df[num_cols[-1]].astype(float)


def compute_sharpe_ratio_simple(equity_df: pd.DataFrame, periods_per_year: int = 252) -> Optional[float]:
    if equity_df is None or len(equity_df) < 3:
        return None
    eq = _get_equity_series(equity_df)
    rets = eq.pct_change().dropna()
    if len(rets) < 2:
        return None
    std = rets.std()
    if std == 0 or pd.isna(std):
        return None
    return float((rets.mean() / std) * (periods_per_year ** 0.5))


def pair_trades(trades: List[Any]) -> List[Dict[str, Any]]:
    """
    bt.trades는 BUY/SELL 순으로 들어온다고 가정하고 페어링.
    반환: [{entry_date, exit_date, entry_price, exit_price, qty, pnl, trade_return}]
    """
    pairs = []
    buy = None
    for t in trades:
        side = getattr(t, "side", None) or getattr(t, "trade_type", None) or getattr(t, "type", None)
        if side == "BUY":
            buy = t
        elif side == "SELL" and buy is not None:
            entry_price = float(getattr(buy, "price"))
            exit_price = float(getattr(t, "price"))
            qty = float(getattr(t, "qty"))
            pnl = float(getattr(t, "pnl", (exit_price - entry_price) * qty))
            denom = entry_price * qty if entry_price * qty != 0 else np.nan
            r = pnl / denom if denom == denom else np.nan
            pairs.append(
                dict(
                    entry_date=pd.to_datetime(getattr(buy, "date")),
                    exit_date=pd.to_datetime(getattr(t, "date")),
                    entry_price=entry_price,
                    exit_price=exit_price,
                    qty=qty,
                    pnl=pnl,
                    trade_return=r,
                )
            )
            buy = None
    return pairs


def _attach_regime(df: pd.DataFrame, regime_series: pd.Series) -> pd.DataFrame:
    """
    df(컬럼에 date가 있는 상태)에 regime 컬럼을 붙인다.
    - df의 각 날짜에 대해 benchmark의 regime을 ffill 방식으로 매핑
    """
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])

    rs = regime_series.copy()
    rs.index = pd.to_datetime(rs.index)

    out["regime"] = (
        rs.reindex(rs.index.union(out["date"]))
        .sort_index()
        .ffill()
        .reindex(out["date"])
        .values
    )
    return out



def run_one_symbol(
    symbol: str,
    bt_config: BacktestConfig,
    strategy: HSMSStrategy,
    initial_cash: int,
    regime_series: pd.Series,
) -> Tuple[pd.DataFrame, List[Any]]:

    df = load_symbol_ohlcv_with_foreign(symbol, use_processed=True)
    df = _ensure_date_index(df).reset_index().rename(columns={"index": "date"})

    # ✅ 여기서 레짐 merge (핵심)
    df = _attach_regime(df, regime_series)

    bt = HSMSSingleBacktester(
        symbol=symbol,
        initial_cash=initial_cash,
        strategy=strategy,
        bt_config=bt_config,
    )

    out = bt.run(df)

    if isinstance(out, pd.DataFrame):
        equity_df = out
        trades = getattr(bt, "trades", [])
    elif isinstance(out, tuple):
        if len(out) == 2:
            equity_df, trades = out
        elif len(out) == 3:
            _, equity_df, trades = out
        else:
            raise ValueError(f"Unexpected tuple len={len(out)} for {symbol}")
    elif isinstance(out, list) and (len(out) == 0 or isinstance(out[0], dict)):
        equity_df = pd.DataFrame(out)
        trades = getattr(bt, "trades", [])
    else:
        raise TypeError(f"Unexpected return type {type(out)} for {symbol}")

    if "date" in equity_df.columns:
        equity_df["date"] = pd.to_datetime(equity_df["date"])
        equity_df = equity_df.sort_values("date")

    return equity_df, trades


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--lookback_days", type=int, default=20)
    ap.add_argument("--min_avg_volume", type=float, default=50_000.0)
    ap.add_argument("--initial_cash", type=int, default=10_000_000)
    ap.add_argument("--out", type=str, default="reports/regime_analysis_top30.csv")
    args = ap.parse_args()

    settings = load_settings()
    trading = settings.get("trading", {})
    regime_cfg = settings.get("regime") or {}

    fill_mode = str(trading.get("fill_mode", "next_open"))

    benchmark_symbol = str(regime_cfg.get("benchmark_symbol", "229200"))
    ma_window = int(regime_cfg.get("ma_window", 200))
    slope_days = int(regime_cfg.get("slope_days", 20))

    # 1) 레짐 테이블 생성
    regime_table = build_regime_table(
        benchmark_symbol=benchmark_symbol,
        ma_window=ma_window,
        slope_days=slope_days,
        use_processed=True,
    )
    regime_table.index = pd.to_datetime(regime_table.index)
    regime_series = regime_table["regime"]

    # 2) 유니버스 선정
    symbols = screen_top_by_volume_volatility(
        lookback_days=args.lookback_days,
        top_n=args.top,
        min_avg_volume=args.min_avg_volume,
    )
    print(f"[REGIME] benchmark={benchmark_symbol} MA={ma_window} slope_days={slope_days}")
    print(f"[REGIME] universe symbols={len(symbols)}")

    # 3) 전략/백테스트 설정
    strategy = HSMSStrategy(
        HSMSConfig(
            ma_window=20,
            momentum_window=5,
            volume_lookback=20,
            volume_multiplier=1.1,
        )
    )
    bt_config = make_bt_config(fill_mode=fill_mode)
    print(f"[REGIME] bt_config={asdict(bt_config)}")

    # 4) 심볼별 백테스트 → 트레이드 페어링 → 레짐 매핑 → 집계
    trade_rows: List[Dict[str, Any]] = []
    symbol_rows: List[Dict[str, Any]] = []

    for sym in symbols:
        try:
            equity_df, trades = run_one_symbol(sym, bt_config, strategy, args.initial_cash, regime_series)

            symbol_rows.append(
                dict(
                    symbol=sym,
                    total_return=compute_total_return(equity_df),
                    mdd=compute_max_drawdown(equity_df),
                    win_rate=compute_win_rate(trades),
                    sharpe=compute_sharpe_ratio_simple(equity_df),
                    trades=len(trades),
                )
            )

            pairs = pair_trades(trades)
            for p in pairs:
                entry_date = p["entry_date"]
                # entry_date 기준으로 레짐 라벨
                regime = (
                    regime_series
                    .reindex(regime_series.index.union([entry_date]))
                    .sort_index()
                    .ffill()
                    .loc[entry_date]
                )
                trade_rows.append(
                    dict(
                        symbol=sym,
                        entry_date=entry_date,
                        exit_date=p["exit_date"],
                        pnl=p["pnl"],
                        trade_return=p["trade_return"],
                        regime=regime,
                    )
                )

        except Exception as e:
            print(f"[SKIP] symbol={sym} err={e}")
            traceback.print_exc()
            break

    trades_df = pd.DataFrame(trade_rows)
    symbols_df = pd.DataFrame(symbol_rows)

    # 5) 레짐별 집계(트레이드 기준)
    if len(trades_df) == 0:
        raise RuntimeError("No paired trades found. (신호/데이터/전략 조건을 확인하세요.)")

    def _win(x: pd.Series) -> float:
        return float((x > 0).mean()) if len(x) else np.nan

    regime_summary = (
        trades_df.groupby("regime")
        .agg(
            trades=("trade_return", "count"),
            win_rate=("trade_return", _win),
            avg_trade_return=("trade_return", "mean"),
            median_trade_return=("trade_return", "median"),
            total_pnl=("pnl", "sum"),
        )
        .reset_index()
        .sort_values("trades", ascending=False)
    )

    print("\n=== Regime Summary (trade-level) ===")
    print(regime_summary)

    # 6) 저장
    import os
    os.makedirs("reports", exist_ok=True)
    regime_summary.to_csv(args.out, index=False, encoding="utf-8-sig")
    trades_df.to_csv("reports/regime_trades_detail.csv", index=False, encoding="utf-8-sig")
    symbols_df.to_csv("reports/regime_symbols_summary.csv", index=False, encoding="utf-8-sig")

    print(f"\n[SAVED] {args.out}")
    print("[SAVED] reports/regime_trades_detail.csv")
    print("[SAVED] reports/regime_symbols_summary.csv")


if __name__ == "__main__":
    main()
