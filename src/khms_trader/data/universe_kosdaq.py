from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

import pandas as pd
from pykrx import stock

from .kis_downloader import download_and_save_symbols
from .kis_downloader import PROJECT_ROOT, DATA_DIR


UNIVERSE_DIR = DATA_DIR / "universe"
UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class KosdaqUniverseConfig:
    """
    코스닥 유니버스 구성 기준 설정.

    - date: 기준 일자 (YYYYMMDD, pykrx 조회용)
    - top_n: 거래대금 기준 상위 N개
    - min_price: 최소 종가 (ex: 1000원 이상)
    - min_traded_value: 최소 일일 거래대금 (원 단위)
    """

    date: str
    top_n: int = 100
    min_price: int = 1_000
    min_traded_value: int = 1_000_000_000  # 10억 이상


def get_kosdaq_universe_df(config: KosdaqUniverseConfig) -> pd.DataFrame:
    """
    주어진 기준에 따라 코스닥 유니버스를 구성하고 DataFrame으로 반환.

    반환 컬럼 예시:
      - ticker: 종목코드 (6자리)
      - name: 종목명
      - close: 종가
      - volume: 거래량
      - traded_value: 거래대금
    """

    # 1) 기준일 코스닥 전체 종목의 시세를 가져온다.
    #    pykrx: get_market_ohlcv_by_ticker(날짜, market="KOSDAQ")
    raw = stock.get_market_ohlcv_by_ticker(config.date, market="KOSDAQ")
    # raw.index: 종목코드, columns: 시가, 고가, 저가, 종가, 거래량, 거래대금, 등락률

    if raw.empty:
        return pd.DataFrame(columns=["ticker", "name", "close", "volume", "traded_value"])

    df = raw.reset_index().rename(
        columns={
            "티커": "ticker",
            "시가": "open",
            "고가": "high",
            "저가": "low",
            "종가": "close",
            "거래량": "volume",
            "거래대금": "traded_value",
        }
    )

    # 2) 종목명 추가
    names = {
        t: stock.get_market_ticker_name(t)
        for t in df["ticker"]
    }
    df["name"] = df["ticker"].map(names)

    # 3) 필터링: 최소 가격, 최소 거래대금
    df = df[df["close"] >= config.min_price]
    df = df[df["traded_value"] >= config.min_traded_value]

    # 4) 거래대금 내림차순 정렬 후 상위 N개 선택
    df = df.sort_values("traded_value", ascending=False).reset_index(drop=True)
    df = df.head(config.top_n)

    # 5) 컬럼 정리
    df = df[["ticker", "name", "close", "volume", "traded_value"]]

    return df


def save_universe_to_csv(df: pd.DataFrame, date: str) -> Path:
    """
    유니버스 DataFrame을 data/universe/kosdaq_{date}.csv 로 저장
    """
    UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)
    path = UNIVERSE_DIR / f"kosdaq_{date}.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"[kosdaq_universe] saved universe: {path} (rows={len(df)})")
    return path


def build_kosdaq_universe(
    date: str,
    top_n: int = 100,
    min_price: int = 1_000,
    min_traded_value: int = 1_000_000_000,
) -> pd.DataFrame:
    """
    코스닥 유니버스를 구성하고 CSV로 저장까지 수행한 뒤, DataFrame을 반환.
    """
    cfg = KosdaqUniverseConfig(
        date=date,
        top_n=top_n,
        min_price=min_price,
        min_traded_value=min_traded_value,
    )
    df = get_kosdaq_universe_df(cfg)
    save_universe_to_csv(df, date)
    return df


def download_kosdaq_universe_data(
    date: str,
    start_date: str,
    end_date: str,
    top_n: int = 100,
    min_price: int = 1_000,
    min_traded_value: int = 1_000_000_000,
) -> None:
    """
    1) 코스닥 유니버스를 구성하고
    2) 해당 유니버스 종목들에 대해 KIS API로 일봉 + 외국인 순매수 데이터를 내려받아
       data/raw/{ticker}.csv 로 저장한다.
    """
    df_univ = build_kosdaq_universe(
        date=date,
        top_n=top_n,
        min_price=min_price,
        min_traded_value=min_traded_value,
    )

    if df_univ.empty:
        print("[kosdaq_universe] universe is empty. nothing to download.")
        return

    symbols: List[str] = df_univ["ticker"].tolist()
    print(f"[kosdaq_universe] universe tickers: {symbols}")

    # KIS API 기반 일봉 + 외국인 순매수 데이터 다운로드
    download_and_save_symbols(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
    )


# --------------------------------------------------
# CLI 진입점
#   예시:
#     1) 유니버스만 생성:
#        python -m khms_trader.data.universe_kosdaq --date 20240201 --top 50
#
#     2) 유니버스 생성 + KIS 데이터 다운로드:
#        python -m khms_trader.data.universe_kosdaq --date 20240201 --top 50 ^
#            --start 20240101 --end 20240201 --download
# --------------------------------------------------
def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="pykrx 기반 코스닥 유니버스 자동 수집 및 (옵션) KIS 데이터 다운로드 유틸리티"
    )
    parser.add_argument(
        "--date",
        required=True,
        help="유니버스 기준 일자 (YYYYMMDD, 예: 20240201)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=100,
        help="거래대금 기준 상위 N개 (default: 100)",
    )
    parser.add_argument(
        "--min-price",
        type=int,
        default=1_000,
        help="최소 종가 (원 단위, default: 1000원)",
    )
    parser.add_argument(
        "--min-traded",
        type=int,
        default=1_000_000_000,
        help="최소 일일 거래대금 (원 단위, default: 10억)",
    )
    parser.add_argument(
        "--start",
        help="(옵션) KIS 데이터 조회 시작일 (YYYYMMDD, --download 사용 시 필수)",
    )
    parser.add_argument(
        "--end",
        help="(옵션) KIS 데이터 조회 종료일 (YYYYMMDD, --download 사용 시 필수)",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="이 플래그를 켜면, 유니버스 종목들에 대해 KIS 일봉+외국인순매수 데이터를 data/raw에 저장",
    )

    args = parser.parse_args()

    if args.download:
        # KIS 데이터까지 내려받는 경우
        if not args.start or not args.end:
            parser.error("--download 옵션 사용 시 --start, --end 둘 다 필요합니다.")
        download_kosdaq_universe_data(
            date=args.date,
            start_date=args.start,
            end_date=args.end,
            top_n=args.top,
            min_price=args.min_price,
            min_traded_value=args.min_traded,
        )
    else:
        # 유니버스만 생성해서 CSV로 저장
        build_kosdaq_universe(
            date=args.date,
            top_n=args.top,
            min_price=args.min_price,
            min_traded_value=args.min_traded,
        )


if __name__ == "__main__":
    main()
