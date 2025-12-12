# scripts/download_from_universe.py
# --------------------------------------------
# universe/kosdaq_YYYYMMDD.csv 의 ticker 목록을 기반으로
# data/raw/{symbol}.csv 를 한 번에 다운로드하는 유틸
# --------------------------------------------

import sys
from pathlib import Path
from typing import List
import time
import pandas as pd

# -----------------------------
# 1) 프로젝트 경로 설정
# -----------------------------
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from khms_trader.data.kis_downloader import (  # type: ignore
    KoreaInvestDataClient,
    load_kis_secrets,
    download_and_save_symbol,
)


DATA_DIR = PROJECT_ROOT / "data"
UNIVERSE_DIR = DATA_DIR / "universe"


def load_universe_tickers(date_str: str) -> List[str]:
    """
    date_str: 'YYYYMMDD' 형식 (예: '20251201')

    data/universe/kosdaq_{date_str}.csv 에서
    ticker 컬럼만 뽑아서 리스트로 반환.
    """
    path = UNIVERSE_DIR / f"kosdaq_{date_str}.csv"
    if not path.exists():
        raise FileNotFoundError(f"[download_from_universe] 유니버스 파일 없음: {path}")

    df = pd.read_csv(path)
    if "ticker" not in df.columns:
        raise KeyError(f"[download_from_universe] 'ticker' 컬럼이 없습니다: {path}")

    tickers = df["ticker"].astype(str).tolist()
    return tickers


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="유니버스 CSV 기반 raw/{symbol}.csv 일괄 다운로드"
    )
    parser.add_argument(
        "--date",
        required=True,
        help="유니버스 기준일 (YYYYMMDD), 예: 20251201 → kosdaq_20251201.csv 사용",
    )
    parser.add_argument(
        "--start",
        required=True,
        help="조회 시작일 (YYYYMMDD)",
    )
    parser.add_argument(
        "--end",
        required=True,
        help="조회 종료일 (YYYYMMDD)",
    )

    args = parser.parse_args()

    date_str = args.date
    start_date = args.start
    end_date = args.end

    print(f"[download_from_universe] 유니버스 기준일: {date_str}")
    print(f"[download_from_universe] 조회 구간: {start_date} ~ {end_date}")

    # 1) 유니버스에서 티커 목록 읽기
    tickers = load_universe_tickers(date_str)
    print(f"[download_from_universe] 유니버스 종목 수: {len(tickers)}")

    # 2) KIS 클라이언트 준비
    secrets = load_kis_secrets()
    client = KoreaInvestDataClient(secrets)

    # 3) 각 종목 다운로드
    for sym in tickers:
        try:
            print(f"[download_from_universe] {sym}: 다운로드 시작...")
            download_and_save_symbol(client, sym, start_date, end_date)
            time.sleep(0.4)
        
        except Exception as e:
            print(f"[download_from_universe] {sym}: 에러 발생 -> {e}")


if __name__ == "__main__":
    main()
