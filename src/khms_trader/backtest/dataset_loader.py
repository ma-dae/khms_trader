# src/khms_trader/backtest/dataset_loader.py

from __future__ import annotations

from pathlib import Path
import pandas as pd

# --------------------------------------------------
# 경로 설정
#   __file__ : src/khms_trader/backtest/dataset_loader.py
#   parents[0] = backtest
#   parents[1] = khms_trader
#   parents[2] = src
#   parents[3] = 프로젝트 루트 (khms_trader)
# --------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
UNIVERSE_DIR = DATA_DIR / "universe"


def load_raw(symbol: str) -> pd.DataFrame:
    """
    종목 코드(예: '005930')에 해당하는 raw CSV를 로딩하는 함수.

    기대 파일 경로:
      data/raw/{symbol}.csv

    컬럼 예시:
      date,open,high,low,close,volume,foreign_net_buy, ...

    반환:
      - date 컬럼을 datetime으로 파싱한 DataFrame
      - date 기준 오름차순 정렬
    """
    path = RAW_DIR / f"{symbol}.csv"
    if not path.exists():
        raise FileNotFoundError(f"[load_raw] 파일이 없습니다: {path}")

    df = pd.read_csv(path)

    # date 컬럼 datetime 변환
    if "date" not in df.columns:
        raise KeyError(f"[load_raw] 'date' 컬럼이 없습니다: {path}")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])

    df = df.sort_values("date").reset_index(drop=True)
    return df


def load_universe(date_str: str) -> pd.DataFrame:
    """
    특정 기준일의 코스닥 유니버스를 로딩하는 함수.

    기대 파일 경로:
      data/universe/kosdaq_{YYYYMMDD}.csv

    예:
      date_str = '20251212'
      → data/universe/kosdaq_20251212.csv

    반환:
      - ticker, name, close, volume, traded_value 등의 컬럼을 가진 DataFrame
    """
    path = UNIVERSE_DIR / f"kosdaq_{date_str}.csv"
    if not path.exists():
        raise FileNotFoundError(f"[load_universe] 파일이 없습니다: {path}")

    df = pd.read_csv(path)
    return df
