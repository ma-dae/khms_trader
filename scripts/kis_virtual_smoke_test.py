# scripts/kis_virtual_smoke_test.py
from __future__ import annotations

from khms_trader.config import load_settings

# ✅ 1) 여기 import 경로/클래스명이 당신 코드와 같아야 합니다.
from khms_trader.broker.korea_invest_api import KoreaInvestBroker # <- 다르면 수정
from khms_trader.broker.base import OrderRequest

def main():
    s = load_settings()

    broker_cfg = s.get("broker") or {}
    provider = broker_cfg.get("provider")
    env = broker_cfg.get("env", "virtual")

    # 여기서 반드시 확인 (이 시점에 None이면 바로 에러로 종료)
    print("[DEBUG] broker_cfg:", broker_cfg)
    print("[DEBUG] provider/env:", provider, env)

    if not provider:
        raise KeyError(f"[FATAL] broker.provider is missing or None. broker_cfg={broker_cfg}")
    
    if provider not in s:
        raise KeyError(f"[FATAL] provider '{provider}' not found in merged settings. top keys={list(s.keys())}")

    if env not in (s.get(provider) or {}):
        raise KeyError(f"[FATAL] env '{env}' not found under '{provider}'. available envs={list((s.get(provider) or {}).keys())}")


    
    creds = s[provider][env]

    app_key = creds["app_key"]
    app_secret = creds["app_secret"]
    account_no = creds["account_no"]
    account_product_code = creds.get("account_product_code")
    base_url = creds["base_url"]

    # ✅ 2) 여기 생성자 인자명이 당신 코드와 같아야 합니다.
    api = KoreaInvestBroker(
        app_key=app_key,
        app_secret=app_secret,
        account_no=account_no,
        account_product_code=account_product_code,
        base_url=base_url,
        virtual=(env == "virtual"),
    )

    print("[1/3] Token OK (if init fetches token)")

    # ✅ 3) 잔고/예수금 조회 함수명은 코드에 맞게 수정
    bal = api.get_cash()  
    print("[2/3] Balance OK")
    print(bal)

    # ✅ 4) 주문 1회: ETF 1주 같은 최소 단위 추천
    symbol = "229200"  # KODEX 코스닥150 (예시)
    qty = 1

    # ✅ 5) 주문 함수명/파라미터는 코드에 맞게 수정
    req = OrderRequest(
        symbol=symbol,
        side="BUY",
        quantity=qty,
        price=15450,
    )

    order_resp = api.place_order(req)
    print("[3/3] Place order OK")
    print(order_resp.success, order_resp.message, order_resp.order_id)


if __name__ == "__main__":
    main()
