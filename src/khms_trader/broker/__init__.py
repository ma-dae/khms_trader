from __future__ import annotations

from typing import Literal

from .base import BaseBroker
from .paper_broker import PaperBroker
from .korea_invest_api import KoreaInvestBroker
from ..config import load_settings, load_secrets


BrokerType = Literal["paper", "korea_invest_virtual", "korea_invest_real"]


def get_broker() -> BaseBroker:
    """
    설정(setting.yaml)에 따라 적절한 브로커 인스턴스를 생성한다.

    broker:
      - paper
      - korea_invest_virtual
      - korea_invest_real
    """
    settings = load_settings()

    broker_type: BrokerType = settings.get("broker", "paper")  # 기본값: paper

    if broker_type == "paper":
        return PaperBroker()

    elif broker_type in ("korea_invest_virtual", "korea_invest_real"):
        secrets = load_secrets()
        ki_conf = secrets.get("korea_invest", {})
        if broker_type == "korea_invest_virtual":
            app_key = ki_conf.get("app_key_virtual")
            app_secret = ki_conf.get("app_secret_virtual")
            account_no = ki_conf.get("account_no_virtual")
            virtual = True
        else:
            app_key = ki_conf.get("app_key_real")
            app_secret = ki_conf.get("app_secret_real")
            account_no = ki_conf.get("account_no_real")
            virtual = False

        if not app_key or not app_secret or not account_no:
            raise ValueError(
                f"{broker_type} requires app_key/app_secret/account_no in secrets.yaml "
                f"under korea_invest section."
            )

        return KoreaInvestBroker(
            app_key=app_key,
            app_secret=app_secret,
            account_no=account_no,
            virtual=virtual,
        )

    else:
        raise ValueError(f"Unknown broker type in setting.yaml: {broker_type}")
