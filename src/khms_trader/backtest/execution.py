from khms_trader.backtest.hsms_single import BacktestConfig

def apply_fill_and_cost(side: str, price: float, qty: int, cfg: BacktestConfig) -> tuple[float, float]:
    """
    return: (fill_price, cost)
    cost는 항상 '현금이 줄어드는 양(+)값'으로 반환.
    """
    notional = price * qty
    slip = cfg.slippage_rate

    if side == "BUY":
        fill_price = price * (1 + slip)
        fee = notional * cfg.fee_rate
        cost = fee + (price * qty * slip)   # 또는 notional*slip로 통일
        return fill_price, cost

    if side == "SELL":
        fill_price = price * (1 - slip)
        fee = notional * cfg.fee_rate
        tax = notional * cfg.tax_rate
        cost = fee + tax + (price * qty * slip)
        return fill_price, cost

    raise ValueError("side must be BUY or SELL")
