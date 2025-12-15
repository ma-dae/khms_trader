from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

# 프로젝트 루트 디렉터리 계산
# 예: /.../khms_trader/src/khms_trader/data/loader.py -> /.../khms_trader
ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT_DIR / "data"
PROCESSED_DIR = DATA_DIR / "processed"
RAW_DIR = DATA_DIR / "raw"

# 만약 CSV 컬럼명이 다르다면 여기서 매핑을 수정하면 된다.
# 예: '날짜' -> 'date', '종가' -> 'close' 등
COLUMN_ALIASES = {
    "date": ["date", "Date", "날짜"],
    "open": ["open", "Open", "시가"],
    "high": ["high", "High", "고가"],
    "low": ["low", "Low", "저가"],
    "close": ["close", "Close", "종가"],
    "volume": ["volume", "Volume", "거래량"],
    "foreign_net_buy": ["foreign_net_buy", "외국인순매수", "외국인_순매수"],
}


def _find_first_existing_column(columns: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    """주어진 candidates 중 실제 DataFrame 컬럼에 존재하는 첫 번째 컬럼명을 반환."""
    col_set = set(columns)
    for name in candidates:
        if name in col_set:
            return name
    return None


def _standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    다양한 컬럼명을 내부 표준 이름으로 통일한다.

    기대 최종 컬럼:
        - date, open, high, low, close, volume, foreign_net_buy
    """
    df = df.copy()
    rename_map: dict[str, str] = {}

    for std_name, aliases in COLUMN_ALIASES.items():
        found = _find_first_existing_column(df.columns, aliases)
        if found is not None and found != std_name:
            rename_map[found] = std_name

    if rename_map:
        df = df.rename(columns=rename_map)

    # 최소 필요 컬럼 체크
    required = {"date", "open", "high", "low", "close", "volume", "foreign_net_buy"}
    missing = required - set(df.columns)
    if missing:
        raise KeyError(f"loader: required columns missing after standardization: {missing}")

    return df


def _read_ohlcv_csv(path: Path) -> pd.DataFrame:
    """
    OHLCV + foreign_net_buy CSV 파일을 읽어온다.

    - date 컬럼을 datetime으로 변환하고 index로 설정
    - 컬럼명 표준화
    - date 기준 오름차순 정렬
    """
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    # date 컬럼명을 아직 모르므로 parse_dates는 읽고 나서 처리
    df = pd.read_csv(
        path,
        encoding="utf-8-sig",
        engine="python",
        on_bad_lines="skip",
    )

    # 컬럼 표준화
    df = _standardize_columns(df)

    # date를 datetime으로 변환
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")

    return df


def load_symbol_ohlcv_with_foreign(
    symbol: str,
    *,
    use_processed: bool = True,
) -> pd.DataFrame:
    """
    심볼(종목코드)에 해당하는 일봉 + 외국인순매수 데이터를 로드한다.

    기본 동작:
        - data/processed/{symbol}.csv 먼저 시도
        - 없으면 data/raw/{symbol}.csv 시도
        - 둘 다 없으면 빈 DataFrame 반환

    CSV 예상 컬럼:
        - date, open, high, low, close, volume, foreign_net_buy
      (실제 컬럼명이 다르면 COLUMN_ALIASES에서 매핑 설정)
    """
    candidates: list[Path] = []

    if use_processed:
        candidates.append(PROCESSED_DIR / f"{symbol}.csv")
    candidates.append(RAW_DIR / f"{symbol}.csv")

    for path in candidates:
        try:
            if path.exists():
                df = _read_ohlcv_csv(path)
                return df
        except Exception as e:
            # 로딩 실패 시 경고만 출력하고 다음 후보 시도
            print(f"[loader] failed to load {path}: {e}")

    # 아무 파일도 없거나 모두 실패한 경우
    print(f"[loader] no data found for symbol={symbol}")
    return pd.DataFrame()
