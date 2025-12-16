# src/khms_trader/utils/time_utils.py
from datetime import datetime
import holidays

kr_holidays = holidays.KR()

def is_trading_day(dt: datetime | None = None) -> bool:
    if dt is None:
        dt = datetime.now()

    # 주말
    if dt.weekday() >= 5:
        return False

    # 공휴일
    if dt.date() in kr_holidays:
        return False

    return True
