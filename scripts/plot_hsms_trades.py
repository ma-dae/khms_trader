# scripts/plot_hsms_trades.py
# --------------------------------------------
# HSMS TOP N 종목에 대해
# - 종가 차트 + 매수/매도 포인트
# - (보조축) 자산곡선(Equity)
# 을 시각화하는 스크립트 (수동)
# --------------------------------------------

import sys
from pathlib import Path
from typing import List, Optional

import matplotlib.pyplot as plt
import pandas as pd

# 1) 프로젝트 / src 경로 세팅
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

# khms_trader 모듈 import
from khms_trader.backtest.dataset_loader import load_raw  # type: ignore
from khms_trader.backtest.hsms_single import HSMSSingleBacktester  # type: ignore
from khms_trader.strategies.hsms import HSMSStrategy, HSMSConfig  # type: ignore


# --------------------------------------------
# 설정: TOP 5 종목 리스트
#   - 필요하면 여기에 심볼 추가/수정해서 다시 실행하면 됨
# --------------------------------------------
TOP5_SYMBOLS = ["347850", "376900", "030530", "226950", "437730"]

INITIAL_CASH = 10_000_000

CONFIG = HSMSConfig(
    ma_window=20,
    momentum_window=5,
    volume_lookback=20,
    volume_multiplier=1.1,
)


def run_backtest_for_symbol(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    심볼 하나에 대해:
      - raw 로딩
      - (옵션) 날짜 필터링
      - HSMS 백테스트 실행
    반환:
      (price_df, equity_df)
    """
    df = load_raw(symbol)

    if start_date is not None:
        start_ts = pd.to_datetime(start_date)
        df = df[df["date"] >= start_ts]
    if end_date is not None:
        end_ts = pd.to_datetime(end_date)
        df = df[df["date"] <= end_ts]

    df = df.sort_values("date").reset_index(drop=True)

    strategy = HSMSStrategy(CONFIG)
    bt = HSMSSingleBacktester(symbol=symbol, initial_cash=INITIAL_CASH, strategy=strategy)
    equity_df = bt.run(df)
    trades = bt.get_trades()

    return df, equity_df, trades


def plot_trades(
    symbol: str,
    name: Optional[str],
    price_df: pd.DataFrame,
    equity_df: pd.DataFrame,
    trades,
    save_dir: Path,
):
    """
    종가 + 매수/매도 포인트 + 자산곡선 시각화
    """
    fig, ax_price = plt.subplots(figsize=(12, 6))

    # 1) 종가 라인
    ax_price.plot(price_df["date"], price_df["close"], label="Close Price", linewidth=1.5)

    # 2) 매수/매도 포인트
    buy_dates = [t.date for t in trades if t.side == "BUY"]
    buy_prices = [t.price for t in trades if t.side == "BUY"]

    sell_dates = [t.date for t in trades if t.side == "SELL"]
    sell_prices = [t.price for t in trades if t.side == "SELL"]

    if buy_dates:
        ax_price.scatter(
            buy_dates,
            buy_prices,
            marker="^",
            color="green",
            s=80,
            label="Buy",
            zorder=3,
        )
    if sell_dates:
        ax_price.scatter(
            sell_dates,
            sell_prices,
            marker="v",
            color="red",
            s=80,
            label="Sell",
            zorder=3,
        )

    ax_price.set_xlabel("Date")
    ax_price.set_ylabel("Price")
    title_name = name if name is not None else symbol
    ax_price.set_title(f"HSMS Trades - {symbol} ({title_name})")

    ax_price.grid(True)

    # 3) 자산곡선(Equity) 보조축
    ax_eq = ax_price.twinx()
    ax_eq.plot(
        equity_df["date"],
        equity_df["equity"],
        linestyle="--",
        color="gray",
        alpha=0.7,
        label="Equity",
    )
    ax_eq.set_ylabel("Equity (KRW)")

    # 4) 범례 정리
    handles_price, labels_price = ax_price.get_legend_handles_labels()
    handles_eq, labels_eq = ax_eq.get_legend_handles_labels()
    handles = handles_price + handles_eq
    labels = labels_price + labels_eq
    ax_price.legend(handles, labels, loc="upper left")

    fig.tight_layout()

    # 5) 저장 경로
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / f"hsms_trades_{symbol}.png"
    fig.savefig(save_path, dpi=150)
    print(f"[PLOT] saved: {save_path}")

    plt.show()
    plt.close(fig)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="HSMS TOP5 종목 매매 구간 시각화 스크립트"
    )
    parser.add_argument(
        "--symbols",
        nargs="*",
        help="직접 심볼 리스트를 지정하고 싶을 때 사용 (예: --symbols 376900 030530)",
    )
    parser.add_argument(
        "--start",
        help="백테스트 시작일 (YYYYMMDD, 옵션)",
    )
    parser.add_argument(
        "--end",
        help="백테스트 종료일 (YYYYMMDD, 옵션)",
    )

    args = parser.parse_args()

    symbols: List[str] = args.symbols if args.symbols else TOP5_SYMBOLS
    start_date = args.start
    end_date = args.end

    print(f"[PLOT] 대상 심볼: {symbols}")
    print(f"[PLOT] 기간: {start_date} ~ {end_date}")

    plots_dir = PROJECT_ROOT / "plots"

    for sym in symbols:
        print(f"[PLOT] {sym} 처리 시작...")
        try:
            price_df, equity_df, trades = run_backtest_for_symbol(
                sym,
                start_date=start_date,
                end_date=end_date,
            )
        except FileNotFoundError:
            print(f"[PLOT] {sym}: raw 데이터 없음 -> 스킵")
            continue
        except Exception as e:
            print(f"[PLOT] {sym}: 백테스트 중 오류 -> {e}")
            continue

        # 이름 정보는 universe 파일을 다시 읽어도 되고,
        # 여기서는 심볼만 타이틀에 사용 (필요하면 확장 가능)
        plot_trades(
            symbol=sym,
            name=None,
            price_df=price_df,
            equity_df=equity_df,
            trades=trades,
            save_dir=plots_dir,
        )


if __name__ == "__main__":
    main()
