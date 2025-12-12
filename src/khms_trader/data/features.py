import pandas as pd
import numpy as np


def calc_ema(series: pd.Series, span: int) -> pd.Series:
    """Exponentially Weighted Moving Average."""
    return series.ewm(span=span, adjust=False).mean()


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Relative Strength Index (RSI) 계산.

    close: 종가 시계열
    period: RSI 기간
    """
    delta = close.diff()

    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)

    gain = pd.Series(gain, index=close.index)
    loss = pd.Series(loss, index=close.index)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / (avg_loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average True Range (ATR) 계산.

    df에는 최소한 'high', 'low', 'close' 컬럼이 있어야 한다.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period, min_periods=period).mean()
    return atr


def add_hsms_features(
    df: pd.DataFrame,
    *,
    rsi_period: int = 14,
    atr_period: int = 14,
    vol_window: int = 20,
    foreign_window: int = 3,
) -> pd.DataFrame:
    """
    HSMS 전략에 필요한 지표/플래그 컬럼을 추가한다.

    요구 컬럼:
        - 'close', 'high', 'low', 'volume', 'foreign_net_buy'
    """
    required_cols = {"close", "high", "low", "volume", "foreign_net_buy"}
    missing = required_cols - set(df.columns)
    if missing:
        raise KeyError(f"add_hsms_features: required columns missing: {missing}")

    out = df.copy()

    # 기본 지표
    out["ema20"] = calc_ema(out["close"], span=20)
    out["ema50"] = calc_ema(out["close"], span=50)
    out["rsi"] = calc_rsi(out["close"], period=rsi_period)
    out["atr"] = calc_atr(out, period=atr_period)
    out["vol_ma20"] = out["volume"].rolling(
        window=vol_window, min_periods=vol_window
    ).mean()

    # 추세 조건
    out["trend_ok"] = (out["ema20"] > out["ema50"]) & (out["close"] > out["ema20"])

    # RSI 50 재돌파
    out["rsi_prev"] = out["rsi"].shift(1)
    out["rsi_cross_50"] = (out["rsi_prev"] < 50) & (out["rsi"] >= 50)

    # 거래량 필터
    out["vol_ok"] = out["volume"] >= out["vol_ma20"] * 1.3

    # 외국인 순매수 롤링 조건 (최근 foreign_window일 중 2일 이상 순매수)
    positive_foreign = out["foreign_net_buy"] > 0
    out["foreign_buy_rolling"] = positive_foreign.rolling(
        window=foreign_window, min_periods=foreign_window
    ).sum()
    out["foreign_trend_ok"] = out["foreign_buy_rolling"] >= 2

    return out
