from __future__ import annotations

from khms_trader.config import load_settings
from khms_trader.broker.korea_invest_api import KoreaInvestBroker, OrderRequest


def main() -> None:
    s = load_settings()

    # KIS virtual 강제
    v = (s.get("korea_invest") or {}).get("virtual") or {}
    required = ["app_key", "app_secret", "account_no", "account_product_code"]
    missing = [k for k in required if not v.get(k)]
    if missing:
        raise KeyError(f"korea_invest.virtual missing keys={missing}")

    api = KoreaInvestBroker(
        app_key=str(v["app_key"]),
        app_secret=str(v["app_secret"]),
        account_no=str(v["account_no"]),
        account_product_code=str(v["account_product_code"]),
        base_url=str(v.get("base_url", "")),
        virtual=True,
    )

    symbol = "229200"
    qty = int(api.get_position(symbol))
    print(f"[STATE] before: {symbol} qty={qty}")

    if qty <= 0:
        print("[DONE] nothing to sell.")
        return

    # ✅ 시장가 전량 매도: price=None
    req = OrderRequest(
        symbol=symbol,
        side="SELL",
        quantity=qty,
        price=15370,   # <-- 시장가
    )
    resp = api.place_order(req)
    print("[ORDER]", resp.success, resp.message, resp.order_id)

    # 재조회
    qty2 = int(api.get_position(symbol))
    print(f"[STATE] after: {symbol} qty={qty2}")


if __name__ == "__main__":
    main()
