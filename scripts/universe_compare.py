import argparse
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from khms_trader.config import load_settings
from khms_trader.backtest.hsms_single import HSMSSingleBacktester, BacktestConfig
from khms_trader.backtest.metrics import (
    compute_total_return,
    compute_max_drawdown,
    compute_win_rate,
)
from khms_trader.strategies.hsms import HSMSStrategy, HSMSConfig
from khms_trader.data.screener import screen_top_by_volume_volatility


def _get_equity_series(equity_df: pd.DataFrame) -> pd.Series:
    """equity 컬럼명이 다를 수 있어 방어적으로 처리"""
    for col in ["equity", "portfolio", "portfolio_value", "value", "total_value"]:
        if col in equity_df.columns:
            return equity_df[col].astype(float)
    # 마지막 방어: 숫자형 컬럼 중 마지막을 equity로 간주
    num_cols = [c for c in equity_df.columns if pd.api.types.is_numeric_dtype(equity_df[c])]
    if not num_cols:
        raise KeyError(f"equity_df에 숫자형 컬럼이 없습니다. columns={list(equity_df.columns)}")
    return equity_df[num_cols[-1]].astype(float)


def compute_sharpe_ratio_simple(equity_df: pd.DataFrame, periods_per_year: int = 252) -> float | None:
    """단순 샤프(무위험 0 가정)"""
    if equity_df is None or len(equity_df) < 3:
        return None
    eq = _get_equity_series(equity_df)
    rets = eq.pct_change().dropna()
    if len(rets) < 2:
        return None
    std = rets.std()
    if std == 0:
        return None
    return float((rets.mean() / std) * (periods_per_year ** 0.5))


def run_one_symbol(
    symbol: str,
    bt_config: BacktestConfig,
    strategy: HSMSStrategy,
    initial_cash: int,
) -> Dict[str, Any]:
    bt = HSMSSingleBacktester(
        symbol=symbol,
        initial_cash=initial_cash,
        strategy=strategy,
        bt_config=bt_config,
    )

    out = bt.run  # run(df)일 수도 있고 run()일 수도 있어 방어적으로 처리

    # df 인자를 요구하는 버전 대응: dataset_loader 대신 기존 로더가 내부에서 로드하는 버전도 존재하므로
    # 우선 run() 호출을 시도하고, TypeError면 run(df)로 전환할 수 있게 설계(여기서는 run() 우선)
    try:
        result = out()
    except TypeError:
        # run(df) 시그니처인 경우: screener/loader 경로를 통일하는 것이 안정적
        # processed→raw로 읽는 로더를 사용(파일 위치 문제 최소화)
        from khms_trader.data.loader import load_symbol_ohlcv_with_foreign

        df = load_symbol_ohlcv_with_foreign(symbol, use_processed=True).copy()
        # 백테스터가 'date'를 기대하면 보정
        if "date" not in df.columns:
            df = df.reset_index().rename(columns={"index": "date"})
        result = out(df)

    # 반환 타입 방어
    if isinstance(result, tuple):
        if len(result) == 2:
            equity_df, trades = result
        elif len(result) == 3:
            _, equity_df, trades = result
        else:
            raise ValueError(f"Unexpected tuple return length={len(result)} for symbol={symbol}")
    elif isinstance(result, pd.DataFrame):
        equity_df = result
        trades = getattr(bt, "trades", [])
    elif isinstance(result, list) and (len(result) == 0 or isinstance(result[0], dict)):
        equity_df = pd.DataFrame(result)
        trades = getattr(bt, "trades", [])
    else:
        raise TypeError(f"Unexpected return type: {type(result)} for symbol={symbol}")

    return {
        "symbol": symbol,
        "total_return": compute_total_return(equity_df),
        "mdd": compute_max_drawdown(equity_df),
        "win_rate": compute_win_rate(trades),
        "sharpe": compute_sharpe_ratio_simple(equity_df),
        "trades": len(trades),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=30, help="스크리너로 고를 상위 종목 수")
    parser.add_argument("--lookback_days", type=int, default=20)
    parser.add_argument("--min_avg_volume", type=float, default=50_000.0)
    parser.add_argument("--initial_cash", type=int, default=10_000_000)
    parser.add_argument("--out", type=str, default="", help="결과 CSV 저장 경로(비우면 reports/ 아래 자동 생성)")
    args = parser.parse_args()

    settings = load_settings()
    trading = settings.get("trading", {})

    # setting.yaml 기반(ON) 파라미터
    base_fill_mode = str(trading.get("fill_mode", "next_open"))
    fee_bps = float(trading.get("fee_bps", 0.0))
    tax_bps = float(trading.get("tax_bps", 0.0))
    slippage_bps = float(trading.get("slippage_bps", 0.0))

    # 전략 설정(원하면 setting.yaml로 옮겨도 됨)
    strategy = HSMSStrategy(
        HSMSConfig(
            ma_window=20,
            momentum_window=5,
            volume_lookback=20,
            volume_multiplier=1.1,
        )
    )

    # 유니버스 선정: live에서 쓰던 스크리너 그대로 사용
    symbols = screen_top_by_volume_volatility(
        lookback_days=args.lookback_days,
        top_n=args.top,
        min_avg_volume=args.min_avg_volume,
    )
    print(f"[STEP2] universe symbols: {len(symbols)}")

    cases: List[Tuple[str, BacktestConfig]] = [
        ("A_next_open_cost_OFF", BacktestConfig(fill_mode="next_open", fee_bps=0.0, tax_bps=0.0, slippage_bps=0.0)),
        ("B_next_open_cost_ON", BacktestConfig(fill_mode="next_open", fee_bps=fee_bps, tax_bps=tax_bps, slippage_bps=slippage_bps)),
        ("C_close_cost_ON", BacktestConfig(fill_mode="close", fee_bps=fee_bps, tax_bps=tax_bps, slippage_bps=slippage_bps)),
    ]

    all_rows: List[Dict[str, Any]] = []
    for case_name, cfg in cases:
        print(f"\n=== Running {case_name} cfg={asdict(cfg)} ===")
        for sym in symbols:
            try:
                row = run_one_symbol(sym, cfg, strategy, args.initial_cash)
                row["case"] = case_name
                row["fill_mode"] = cfg.fill_mode
                all_rows.append(row)
            except Exception as e:
                print(f"[SKIP] {case_name} symbol={sym} err={e}")

    df = pd.DataFrame(all_rows)

    # 요약(케이스별 평균/중앙값)
    summary = (
        df.groupby("case")[["total_return", "mdd", "win_rate", "sharpe", "trades"]]
        .agg(["mean", "median", "count"])
    )

    print("\n=== Summary (by case) ===")
    print(summary)

    out_path = args.out.strip()
    if not out_path:
        Path("reports").mkdir(exist_ok=True)
        out_path = f"reports/step2_universe_compare_top{args.top}.csv"

    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n[SAVED] {out_path}")


if __name__ == "__main__":
    main()
