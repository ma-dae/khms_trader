from __future__ import annotations

from khms_trader.config import load_settings
from khms_trader.broker.paper_broker import PaperBroker
from khms_trader.broker.korea_invest_api import KoreaInvestBroker


def make_broker():
    s = load_settings()
    b = s.get("broker") or {}
    name = str(b.get("name", "paper")).lower()

    if name == "paper":
        return PaperBroker()

    if name in ("korea_invest_virtual", "kis_virtual"):
        # secrets.yaml에서 병합되어 들어오는 값들
        app_key = b["app_key"]
        app_secret = b["app_secret"]
        account_no = b["account_no"]
        base_url = b["base_url"]
        virtual = bool(b.get("virtual", True))

        return KoreaInvestBroker(
            app_key=app_key,
            app_secret=app_secret,
            account_no=account_no,
            base_url=base_url,
            virtual=virtual,
        )

    raise ValueError(f"Unknown broker.name: {name}")
