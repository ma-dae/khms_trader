# scripts/test_hsms.py
# --------------------------------------------
# HSMS 단일 종목 백테스트 실행 스크립트
# --------------------------------------------

import sys
from pathlib import Path

import matplotlib.pyplot as plt

# 1) 프로젝트 / src 경로 세팅
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

# 2) khms_trader 모듈 import
from khms_trader.backtest.dataset_loader import load_raw
from khms_trader.backtest.hsms_single import HSMSSingleBacktester
from khms_trader.backtest.metrics import (
    compute_total_return,
    compute_max_drawdown,
    compute_win_rate,
)
from khms_trader.strategies.hsms import HSMSStrategy, HSMSConfig


SYMBOL = "005930"
CASH = 10_000_000
CONFIG = HSMSConfig(
    ma_window=20,
    momentum_window=5,
    volume_lookback=20,
    volume_multiplier=1.1,
)


def main():
    print(f"[TEST] HSMS 단일 종목 백테스트 — 종목: {SYMBOL}")

    # 1) 데이터 로딩
    df = load_raw(SYMBOL)
    print(f"[DATA] raw 로딩 완료: {len(df)} rows")

    # 2) 전략 & 백테스터 준비
    strategy = HSMSStrategy(CONFIG)
    bt = HSMSSingleBacktester(symbol=SYMBOL, initial_cash=CASH, strategy=strategy)

    # 3) 백테스트 실행
    equity_df = bt.run(df)
    trades = bt.get_trades()

    print("\n[RESULT] equity_df tail(10):")
    print(equity_df.tail(10))

    # 4) 성과 지표 계산
    total_ret = compute_total_return(equity_df)
    mdd = compute_max_drawdown(equity_df)
    win_rate = compute_win_rate(trades)

    print("\n[METRICS]")
    print(f" - 초기 자산: {CASH:,.0f}원")
    print(f" - 최종 자산: {equity_df['equity'].iloc[-1]:,.0f}원")
    print(f" - 총 수익률: {total_ret * 100:.2f}%")
    print(f" - 최대 낙폭(MDD): {mdd * 100:.2f}%")
    if win_rate is not None:
        print(f" - 승률(매도 기준): {win_rate * 100:.2f}%")
    else:
        print(" - 승률: 트레이드 없음")

    # 5) 자산곡선 시각화
    plt.figure(figsize=(12, 6))
    plt.plot(equity_df["date"], equity_df["equity"], label="Equity")
    plt.title(f"HSMS Backtest Equity Curve — {SYMBOL}")
    plt.xlabel("Date")
    plt.ylabel("Equity (KRW)")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
