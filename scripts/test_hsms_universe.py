# scripts/test_hsms_universe.py
# --------------------------------------------
# 코스닥 유니버스(특정 날짜) 기준
# 각 심볼 HSMS 백테스트 후 성과 랭킹 TOP 5 출력 스크립트
# --------------------------------------------

import sys
from pathlib import Path

import pandas as pd

# 1) 프로젝트 / src 경로 세팅
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from khms_trader.backtest.hsms_universe import HSMSUniverseBacktester
from khms_trader.strategies.hsms import HSMSConfig


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="HSMS 유니버스 백테스트 (각 심볼 성과 랭킹 TOP N)"
    )
    parser.add_argument(
        "--date",
        required=True,
        help="유니버스 기준일 (YYYYMMDD), 예: 20251201 → kosdaq_20251201.csv 사용",
    )
    parser.add_argument(
        "--start",
        help="백테스트 시작일 (YYYYMMDD, 옵션)",
    )
    parser.add_argument(
        "--end",
        help="백테스트 종료일 (YYYYMMDD, 옵션)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="랭킹 상위 N개 출력 (기본: 5)",
    )

    args = parser.parse_args()

    universe_date = args.date
    start_date = args.start
    end_date = args.end
    top_n = args.top

    print(f"[TEST] HSMS 유니버스 백테스트 시작")
    print(f" - universe date : {universe_date}")
    print(f" - backtest range: {start_date} ~ {end_date}")

    config = HSMSConfig(
        ma_window=20,
        momentum_window=5,
        volume_lookback=20,
        volume_multiplier=1.1,
    )

    bt_uni = HSMSUniverseBacktester(
        universe_date=universe_date,
        start_date=start_date,
        end_date=end_date,
        initial_cash=10_000_000,
        config=config,
    )

    df_res = bt_uni.run()

    if df_res.empty:
        print("[RESULT] 유효한 결과가 없습니다. (데이터 부족 / 모든 종목 스킵)")
        return

    # total_return 기준 내림차순 정렬
    df_res_sorted = df_res.sort_values("total_return", ascending=False).reset_index(drop=True)

    print("\n[RESULT] 전체 종목 성과 상위 10개 (total_return 기준):")
    print(
        df_res_sorted[["symbol", "name", "total_return", "mdd", "win_rate", "final_equity", "n_trades"]]
        .head(10)
        .to_string(index=False, float_format=lambda x: f"{x:.4f}")
    )

    print(f"\n[TOP {top_n}] 랭킹 (total_return 기준):")
    top_df = df_res_sorted.head(top_n).copy()
    # 퍼센트 보기 좋게 변환
    top_df["total_return_pct"] = top_df["total_return"] * 100
    top_df["mdd_pct"] = top_df["mdd"] * 100
    if "win_rate" in top_df.columns:
        top_df["win_rate_pct"] = top_df["win_rate"] * 100

    print(
        top_df[
            ["symbol", "name", "total_return_pct", "mdd_pct", "win_rate_pct", "final_equity", "n_trades"]
        ].to_string(index=False, float_format=lambda x: f"{x:.2f}")
    )


if __name__ == "__main__":
    main()
