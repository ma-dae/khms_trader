from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd

from .loader import PROCESSED_DIR, RAW_DIR, _read_ohlcv_csv


def list_available_symbols() -> List[str]:
    """
    data/processed, data/raw 아래의 CSV 파일명을 스캔해서
    사용 가능한 심볼 목록을 반환한다.

    예:
        data/processed/005930.csv -> "005930"
        data/raw/000660.csv      -> "000660"
    """
    symbols = set()

    for directory in [PROCESSED_DIR, RAW_DIR]:
        if not directory.exists():
            continue

        for path in directory.glob("*.csv"):
            symbols.add(path.stem)

    return sorted(symbols)


def _load_recent_data(symbol: str, lookback_days: int) -> pd.DataFrame:
    """
    개별 심볼의 최근 lookback_days 일 데이터를 로드한다.
    loader._read_ohlcv_csv를 그대로 활용.
    """
    # 우선 processed 우선, 없으면 raw
    candidates: List[Path] = [
        PROCESSED_DIR / f"{symbol}.csv",
        RAW_DIR / f"{symbol}.csv",
    ]

    for path in candidates:
        if path.exists():
            df = _read_ohlcv_csv(path)
            # 최신 일 기준으로 lookback_days만 슬라이싱
            if len(df) == 0:
                return df
            last_date = df.index.max()
            start_date = last_date - timedelta(days=lookback_days * 2)
            # 주말 등 비거래일을 감안해서 2배로 넉넉히 자른 뒤,
            # tail(lookback_days)로 다시 줄일 수도 있다.
            df_recent = df[df.index >= start_date].tail(lookback_days)
            return df_recent

    return pd.DataFrame()


def screen_top_by_volume_volatility(
    *,
    lookback_days: int = 20,
    top_n: int = 20,
    min_price: float = 1_000.0,
    min_avg_volume: float = 10_000.0,
) -> List[str]:
    """
    거래대금·변동성 기반 자동 스크리너.

    - data 폴더의 모든 심볼을 대상으로
    - 최근 lookback_days 동안의
        - 평균 거래량
        - 변동성(일간 수익률 표준편차)
      을 계산한 뒤,
    - 기본 필터(min_price, min_avg_volume)를 통과하는 심볼 중
    - score = avg_volume * volatility 로 점수를 매겨
    - 상위 top_n 개 심볼을 반환한다.
    """
    symbols = list_available_symbols()
    print(f"[screener] 발견된 심볼 수: {len(symbols)}")

    rows: List[Tuple[str, float, float, float]] = []  # (symbol, avg_volume, volatility, score)

    for symbol in symbols:
        df = _load_recent_data(symbol, lookback_days=lookback_days)
        if df.empty:
            continue

        close = df["close"]
        volume = df["volume"]

        if len(close) < 5:
            # 데이터가 너무 짧으면 스킵
            continue

        # 일간 수익률
        ret = close.pct_change().dropna()
        volatility = float(ret.std())
        avg_volume = float(volume.mean())
        avg_price = float(close.mean())

        # 기본 필터 (너무 싸거나, 거래량이 너무 적은 종목 제외)
        if avg_price < min_price:
            continue
        if avg_volume < min_avg_volume:
            continue

        score = avg_volume * volatility
        rows.append((symbol, avg_volume, volatility, score))

    if not rows:
        print("[screener] 조건을 만족하는 심볼이 없습니다.")
        return []

    df_score = pd.DataFrame(rows, columns=["symbol", "avg_volume", "volatility", "score"])
    df_score = df_score.sort_values("score", ascending=False)

    print("[screener] 상위 심볼 예시:")
    print(df_score.head(min(top_n, 10)))

    top_symbols = df_score["symbol"].head(top_n).tolist()
    print(f"[screener] 선택된 심볼({len(top_symbols)}개): {top_symbols}")

    return top_symbols
