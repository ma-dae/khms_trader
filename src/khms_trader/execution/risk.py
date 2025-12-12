# 종목당 자본의 X%만 사용, 가격으로 나누기
from __future__ import annotations

from math import floor


def calc_position_size_by_ratio(
    cash: float,
    price: float,
    ratio: float = 0.1,
) -> int:
    """
    자본 비율(ratio)에 따라 매수 수량을 결정.

    예:
        cash = 10,000,000, ratio = 0.1 이고
        price = 50,000 이라면
        -> 1,000,000 / 50,000 = 20주
    """
    if price <= 0 or cash <= 0 or ratio <= 0:
        return 0

    target_cash = cash * ratio
    qty = floor(target_cash / price)
    return max(qty, 0)
