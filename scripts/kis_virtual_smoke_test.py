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

    print("[DEBUG] broker_cfg:", broker_cfg)
    print("[DEBUG] broker.provider/env (trading):", provider, env)

    # ✅ 스모크 테스트 목적 명시 (혼선 방지)
    print("[INFO] This smoke test validates KIS VIRTUAL connectivity regardless of broker.provider.")

    # ✅ 핵심: provider/env로 creds를 찾지 말고, korea_invest.virtual을 직접 본다
    ki = s.get("korea_invest") or {}
    creds = ki.get("virtual") or {}

    # 필수키 검증
    required = ["app_key", "app_secret", "account_no", "account_product_code"]
    missing = [k for k in required if not creds.get(k)]
    if missing:
        raise KeyError(
            f"[FATAL] missing keys in settings['korea_invest']['virtual']: {missing}. "
            f"available={list(creds.keys())}"
        )

    app_key = creds["app_key"]
    app_secret = creds["app_secret"]
    account_no = creds["account_no"]
    account_product_code = creds.get("account_product_code")

    # base_url은 코드가 내부에서 virtual이면 vts로 고정한다면 굳이 필요 없고,
    # 필요하면 secrets.yaml에 넣고 여기서 읽어도 됨.
    base_url = creds.get("base_url")  # optional

    # ✅ 여기서 virtual=True 강제
    api = KoreaInvestBroker(
        app_key=app_key,
        app_secret=app_secret,
        account_no=account_no,
        account_product_code=account_product_code,
        base_url=base_url,
        virtual=True,
    )

    print("[1/3] Token OK (if init fetches token)")

    bal = api.get_cash()
    print("[2/3] Balance OK")
    print(bal)

    symbol = "229200"
    qty = 1

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
