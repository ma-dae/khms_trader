# src/khms_trader/broker/factory.py


from __future__ import annotations

from khms_trader.config import load_settings
from khms_trader.broker.paper_broker import PaperBroker
from khms_trader.broker.korea_invest_api import KoreaInvestBroker


def make_broker():
    s = load_settings()
    cfg = s.get("broker", {})

    provider = cfg.get("provider")
    env = cfg.get("env")

    # 1) PAPER
    if provider == "paper":
        return PaperBroker()

    # 2) KOREA INVEST
    if provider == "korea_invest":
        kis = (s.get("korea_invest") or {}).get(env)
        if not kis:
            raise KeyError(f"korea_invest.{env} not found in secrets.yaml")

        return KoreaInvestBroker(
            app_key=kis["app_key"],
            app_secret=kis["app_secret"],
            account_no=kis["account_no"],
            account_product_code=kis["account_product_code"],
            base_url=kis["base_url"],
            virtual=(env == "virtual"),
        )

    raise ValueError(f"Unknown broker.provider={provider}")
