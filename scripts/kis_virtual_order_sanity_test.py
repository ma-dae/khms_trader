# scripts/kis_virtual_order_sanity_test.py
from __future__ import annotations

import argparse
import time
from typing import Any, Callable, Optional

from khms_trader.config import load_settings
from khms_trader.broker.korea_invest_api import KoreaInvestBroker
from khms_trader.broker.base import OrderRequest


def _pick_provider_env(s: dict) -> tuple[str, str]:
    broker_cfg = s.get("broker") or {}
    provider = broker_cfg.get("provider") or broker_cfg.get("name")
    env = broker_cfg.get("env") or "virtual"
    if not provider:
        raise KeyError(f"broker.provider missing. broker={broker_cfg}")
    return provider, env


def _make_broker(s: dict) -> KoreaInvestBroker:
    provider, env = _pick_provider_env(s)
    if provider != "korea_invest":
        raise ValueError(f"This sanity test is for korea_invest only. got provider={provider}")

    creds = s["korea_invest"][env]
    app_key = creds["app_key"]
    app_secret = creds["app_secret"]
    account_no = creds["account_no"]
    account_product_code = (creds.get("account_product_code") or "01")

    base_url = (creds.get("base_url") or "").strip()
    if not base_url:
        base_url = (
            "https://openapivts.koreainvestment.com:29443"
            if env == "virtual"
            else "https://openapi.koreainvestment.com:9443"
        )

    return KoreaInvestBroker(
        app_key=app_key,
        app_secret=app_secret,
        account_no=account_no,
        account_product_code=account_product_code,
        base_url=base_url,
        virtual=(env == "virtual"),
    )


def _call_first_method(obj: Any, method_names: list[str], *args, **kwargs) -> tuple[Optional[str], Any]:
    """
    obj 에서 method_names 중 존재하는 첫 메서드를 찾아 호출.
    (찾은 메서드명, 결과) 반환. 없으면 (None, None).
    """
    for name in method_names:
        fn = getattr(obj, name, None)
        if callable(fn):
            return name, fn(*args, **kwargs)
    return None, None


def main() -> None:
    p = argparse.ArgumentParser(description="KIS virtual order sanity test (optional fill/position checks)")
    p.add_argument("--symbol", default="005930", help="PDNO (e.g., 005930)")
    p.add_argument("--qty", type=int, default=1, help="Order quantity")
    p.add_argument("--price", type=float, default=None, help="Limit price. If omitted, broker should map to market order.")
    p.add_argument("--wait-seconds", type=int, default=15, help="Total seconds to poll for order/position updates")
    p.add_argument("--poll-interval", type=float, default=3.0, help="Seconds between polls")
    p.add_argument("--no-order", action="store_true", help="Skip placing an order; just query balance/positions if supported")
    args = p.parse_args()

    s = load_settings()
    api = _make_broker(s)

    print("[0/4] Broker init OK:", api.__class__.__name__)

    # (옵션) 현금 조회
    cash_method, cash = _call_first_method(api, ["get_cash", "cash", "get_available_cash"])
    if cash_method:
        print(f"[1/4] Cash OK via {cash_method}: {cash}")
    else:
        print("[1/4] Cash SKIP (no method found). Expected one of: get_cash/cash/get_available_cash")

    order_id: Optional[str] = None

    if not args.no_order:
        req = OrderRequest(
            symbol=args.symbol,
            side="BUY",
            quantity=args.qty,
            price=args.price,
        )
        order_resp = api.place_order(req)
        # OrderResult 필드명은 프로젝트 계약에 따라 다를 수 있어 안전하게 접근
        ok = getattr(order_resp, "success", None)
        msg = getattr(order_resp, "message", None)
        oid = getattr(order_resp, "order_id", None)

        print(f"[2/4] Place order response: ok={ok} message={msg} order_id={oid}")

        if not ok:
            raise RuntimeError(f"Order rejected: {msg}")

        order_id = str(oid) if oid is not None else None
        if not order_id:
            print("[WARN] order_id not found on OrderResult. (Cannot do order-status polling without it.)")

    # ---- (옵션) 주문 상태/미체결/체결 조회 폴링 ----
    # 프로젝트마다 메서드명이 다를 수 있어 후보들을 넓게 잡음
    order_query_methods = [
        "get_order", "get_order_status", "inquire_order", "inquire_orders",
        "get_open_orders", "list_open_orders", "open_orders",
        "get_unfilled_orders", "list_unfilled_orders", "unfilled_orders",
    ]

    # ---- (옵션) 보유잔고/포지션 조회 ----
    position_methods = [
        "get_positions", "positions", "get_holdings", "holdings", "get_portfolio", "portfolio",
        "inquire_balance", "get_balance_detail",
    ]

    if args.wait_seconds <= 0:
        print("[3/4] Poll SKIP (wait_seconds<=0)")
        print("[4/4] Done")
        return

    deadline = time.time() + args.wait_seconds
    done = False
    print(f"[3/4] Polling up to {args.wait_seconds}s (interval {args.poll_interval}s) ...")

    last_order_info = None
    last_pos_info = None

    while time.time() < deadline and not done:
        # 주문 상태 조회(가능하면)
        m, info = _call_first_method(api, order_query_methods, order_id)

        if m and isinstance(info, dict) and info.get("found"):
            ord_qty = info.get("ord_qty")
            filled = info.get("filled_qty")
            unfilled = info.get("unfilled_qty")
            avg_price = None

            rec = info.get("record") or {}
            avg_price = rec.get("avg_prvs")
            pos = api.get_positions() or {}
            held = pos.get(args.symbol, 0)

            print(
                f"  [ORDER] {order_id} | "
                f"filled= {filled}/{ord_qty} | "
                f"unfilled= {unfilled} | "
                f"avg_price={avg_price}"
                f" | held={held}"
            )

            if filled is not None and ord_qty is not None and filled >= ord_qty:
                print(" → Order fully filled. Stop polling. ")
                done = True
                break
        else:
            print("  [ORDER] status not available yet")

        time.sleep(args.poll_interval)    
        
    print("[4/4] Done")

    if not last_order_info:
        print(
            "\n[NOTE] To confirm fills, add one of these methods to KoreaInvestBroker:\n"
            "  - get_order_status(order_id)  OR  get_open_orders()  OR  get_unfilled_orders()\n"
            "Then this script will automatically pick it up."
        )
    if not last_pos_info:
        print(
            "\n[NOTE] To confirm holdings/positions, add one of these methods:\n"
            "  - get_positions() OR get_holdings() OR inquire_balance()"
        )


if __name__ == "__main__":
    main()
