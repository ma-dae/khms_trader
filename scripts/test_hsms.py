# scripts/test_hsms.py

from __future__ import annotations

import argparse
import pandas as pd

from khms_trader.config import load_settings
from khms_trader.backtest.dataset_loader import load_raw
from khms_trader.backtest.metrics import (
    compute_total_return,
    compute_max_drawdown,
    compute_win_rate,
    compute_sharpe_ratio,
)
from khms_trader.backtest.hsms_single import HSMSSingleBacktester
from khms_trader.backtest.configs import BacktestConfig
from khms_trader.backtest.bt_config_factory import make_test_cases
from khms_trader.strategies.hsms import HSMSStrategy, HSMSConfig


# -----------------------------
# 실험 대상 심볼 (단일 종목 sanity check)
# -----------------------------
SYMBOL = "376900"   # 코스닥 기준 종목


def run_one_case(
    name: str,
    bt_config: BacktestConfig,
    df: pd.DataFrame,
    initial_cash: int,
) -> dict:
    """
    단일 케이스 실행 및 성과 요약
    """
    strategy = HSMSStrategy(
        HSMSConfig(
            ma_window=20,
            momentum_window=5,
            volume_lookback=20,
            volume_multiplier=1.1,
        )
    )

    bt = HSMSSingleBacktester(
        symbol=SYMBOL,
        initial_cash=initial_cash,
        strategy=strategy,
        bt_config=bt_config,
    )

    equity_df = bt.run(df)
    trades = bt.get_trades()

    total_return = compute_total_return(equity_df)
    mdd = compute_max_drawdown(equity_df)
    win_rate = compute_win_rate(trades)
    sharpe = compute_sharpe_ratio(equity_df)
    final_equity = float(equity_df["equity"].iloc[-1])
    n_trades = len([t for t in trades if t.side == "SELL"])

    return {
        "case": name,
        "fill_mode": bt_config.fill_mode,
        "fee_bps": bt_config.fee_bps,
        "tax_bps": bt_config.tax_bps,
        "slippage_bps": bt_config.slippage_bps,
        "total_return": total_return,
        "mdd": mdd,
        "win_rate": win_rate,
        "sharpe": sharpe,
        "final_equity": final_equity,
        "trades": n_trades,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--initial_cash", type=int, default=10_000_000)
    args = parser.parse_args()

    # -----------------------------
    # 1) 데이터 로딩
    # -----------------------------
    df = load_raw(SYMBOL)
    if df.empty:
        raise RuntimeError(f"{SYMBOL}: raw 데이터가 비어 있습니다.")

    # -----------------------------
    # 2) 설정 기반 테스트 케이스 생성
    # -----------------------------
    settings = load_settings()
    cases = make_test_cases(settings=settings)

    # -----------------------------
    # 3) 케이스별 실행
    # -----------------------------
    results = []
    for name, cfg in cases:
        print(f"\n=== Running {name} ===")
        res = run_one_case(
            name=name,
            bt_config=cfg,
            df=df,
            initial_cash=args.initial_cash,
        )
        print(res)
        results.append(res)

    # -----------------------------
    # 4) 요약 출력
    # -----------------------------
    df_res = pd.DataFrame(results)
    print("\n=== Summary ===")
    print(
        df_res[
            [
                "case",
                "fill_mode",
                "total_return",
                "mdd",
                "win_rate",
                "sharpe",
                "trades",
                "final_equity",
            ]
        ]
    )


if __name__ == "__main__":
    main()
