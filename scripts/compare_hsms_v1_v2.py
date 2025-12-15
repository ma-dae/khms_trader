# scripts/compare_hsms_v1_v2.py
# --------------------------------------------
# HSMS 1.0 vs HSMS 2.0 유니버스 백테스트 비교 스크립트
# - 동일 기간/유니버스로 두 전략을 실행
# - Top N 랭킹 비교
# - 공통 종목에 대해 성과 차이 비교
# - 요약 통계 출력
# --------------------------------------------

import sys
from pathlib import Path

import pandas as pd

# 프로젝트 / src 경로 세팅
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from khms_trader.backtest.hsms_universe import HSMSUniverseBacktester
from khms_trader.strategies.hsms import HSMSStrategy, HSMSConfig, HSMS2Strategy, HSMS2Config


def run_universe(
    universe_date: str,
    start: str | None,
    end: str | None,
    mode: str,
) -> pd.DataFrame:
    """
    mode: 'v1' or 'v2'
    """
    if mode == "v1":
        cfg = HSMSConfig(
            ma_window=20,
            momentum_window=5,
            volume_lookback=20,
            volume_multiplier=1.1,
        )
        strategy_cls = HSMSStrategy
        strategy_cfg = cfg
        label = "HSMS 1.0"
    elif mode == "v2":
        cfg = HSMS2Config(
            ma_window=20,
            momentum_window=5,
            volume_lookback=20,
            volume_multiplier=1.1,
            foreign_lookback=5,
            foreign_min_sum=0.0,
        )
        strategy_cls = HSMS2Strategy
        strategy_cfg = cfg
        label = "HSMS 2.0"
    else:
        raise ValueError("mode must be 'v1' or 'v2'")

    print(f"\n==============================")
    print(f"[RUN] {label}")
    print(f" - universe: {universe_date}")
    print(f" - range   : {start} ~ {end}")
    print(f"==============================")

    bt = HSMSUniverseBacktester(
        universe_date=universe_date,
        start_date=start,
        end_date=end,
        initial_cash=10_000_000,
        strategy_cls=strategy_cls,
        strategy_config=strategy_cfg,
    )

    df = bt.run()
    if df.empty:
        print(f"[RUN] {label}: 결과 없음")
        return df

    df = df.copy()
    df["strategy"] = label
    return df


def print_top(df: pd.DataFrame, top_n: int, title: str) -> pd.DataFrame:
    if df.empty:
        print(f"\n[{title}] 결과 없음")
        return df

    df_sorted = df.sort_values("total_return", ascending=False).reset_index(drop=True)
    top = df_sorted.head(top_n).copy()

    # 보기 좋게 퍼센트화
    top["total_return_pct"] = top["total_return"] * 100
    top["mdd_pct"] = top["mdd"] * 100
    top["win_rate_pct"] = top["win_rate"] * 100

    print(f"\n[{title}] TOP {top_n}")
    print(
        top[
            ["symbol", "name", "total_return_pct", "mdd_pct", "win_rate_pct", "final_equity", "n_trades"]
        ].to_string(index=False, float_format=lambda x: f"{x:.2f}")
    )
    return top


def summary_stats(df: pd.DataFrame, title: str) -> None:
    if df.empty:
        print(f"\n[{title}] 요약: 결과 없음")
        return

    # 간단 요약: 중앙값/평균
    # (수익률 분포가 왜곡될 수 있어 median을 같이 봄)
    ret_mean = df["total_return"].mean()
    ret_med = df["total_return"].median()
    mdd_mean = df["mdd"].mean()
    mdd_med = df["mdd"].median()
    trades_mean = df["n_trades"].mean()

    print(f"\n[{title}] 요약 통계")
    print(f" - 종목 수: {len(df)}")
    print(f" - 평균 수익률: {ret_mean*100:.2f}% / 중앙값 수익률: {ret_med*100:.2f}%")
    print(f" - 평균 MDD  : {mdd_mean*100:.2f}% / 중앙값 MDD  : {mdd_med*100:.2f}%")
    print(f" - 평균 매도 트레이드 수: {trades_mean:.2f}")


def compare_common(v1: pd.DataFrame, v2: pd.DataFrame, top_n: int) -> None:
    """
    공통 종목(교집합)에 대해 성과 차이를 계산
    """
    if v1.empty or v2.empty:
        print("\n[COMPARE] 공통 비교 불가 (한쪽 결과 없음)")
        return

    m1 = v1[["symbol", "name", "total_return", "mdd", "win_rate", "n_trades"]].copy()
    m2 = v2[["symbol", "name", "total_return", "mdd", "win_rate", "n_trades"]].copy()

    merged = pd.merge(m1, m2, on=["symbol", "name"], suffixes=("_v1", "_v2"))
    if merged.empty:
        print("\n[COMPARE] 공통 종목 없음")
        return

    merged["ret_diff"] = merged["total_return_v2"] - merged["total_return_v1"]
    merged["mdd_diff"] = merged["mdd_v2"] - merged["mdd_v1"]
    merged["trades_diff"] = merged["n_trades_v2"] - merged["n_trades_v1"]

    merged_sorted = merged.sort_values("ret_diff", ascending=False).reset_index(drop=True)

    print(f"\n[COMPARE] HSMS 2.0 - 1.0 수익률 개선 TOP {top_n} (공통 종목 기준)")
    tmp = merged_sorted.head(top_n).copy()
    tmp["ret_diff_pct"] = tmp["ret_diff"] * 100
    tmp["mdd_diff_pct"] = tmp["mdd_diff"] * 100
    print(
        tmp[
            ["symbol", "name", "ret_diff_pct", "mdd_diff_pct", "trades_diff"]
        ].to_string(index=False, float_format=lambda x: f"{x:.2f}")
    )

    print(f"\n[COMPARE] HSMS 2.0 - 1.0 수익률 악화 TOP {top_n} (공통 종목 기준)")
    tmp2 = merged_sorted.tail(top_n).copy()
    tmp2 = tmp2.sort_values("ret_diff", ascending=True)
    tmp2["ret_diff_pct"] = tmp2["ret_diff"] * 100
    tmp2["mdd_diff_pct"] = tmp2["mdd_diff"] * 100
    print(
        tmp2[
            ["symbol", "name", "ret_diff_pct", "mdd_diff_pct", "trades_diff"]
        ].to_string(index=False, float_format=lambda x: f"{x:.2f}")
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="HSMS 1.0 vs 2.0 유니버스 성과 비교")
    parser.add_argument("--date", required=True, help="유니버스 기준일 YYYYMMDD")
    parser.add_argument("--start", help="백테스트 시작일 YYYYMMDD")
    parser.add_argument("--end", help="백테스트 종료일 YYYYMMDD")
    parser.add_argument("--top", type=int, default=5, help="TOP N 출력")
    parser.add_argument("--save", action="store_true", help="결과 CSV 저장")

    args = parser.parse_args()

    v1 = run_universe(args.date, args.start, args.end, mode="v1")
    v2 = run_universe(args.date, args.start, args.end, mode="v2")

    # TOP 출력
    top_v1 = print_top(v1, args.top, "HSMS 1.0")
    top_v2 = print_top(v2, args.top, "HSMS 2.0")

    # 요약 통계
    summary_stats(v1, "HSMS 1.0")
    summary_stats(v2, "HSMS 2.0")

    # 공통 종목 비교
    compare_common(v1, v2, top_n=args.top)

    if args.save:
        out_dir = PROJECT_ROOT / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        if not v1.empty:
            v1.to_csv(out_dir / f"hsms_v1_{args.date}_{args.start}_{args.end}.csv", index=False, encoding="utf-8-sig")
        if not v2.empty:
            v2.to_csv(out_dir / f"hsms_v2_{args.date}_{args.start}_{args.end}.csv", index=False, encoding="utf-8-sig")
        print(f"\n[SAVE] reports/ 폴더에 CSV 저장 완료")


if __name__ == "__main__":
    main()
