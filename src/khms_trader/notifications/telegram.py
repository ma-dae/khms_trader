from __future__ import annotations

import requests
from dataclasses import dataclass

from khms_trader.config import load_settings


@dataclass(frozen=True)
class TelegramConfig:
    enabled: bool
    token: str
    chat_id: str


class TelegramNotifier:
    def __init__(self) -> None:
        settings = load_settings()
        tg = (settings.get("telegram") or {})  # dict 안전 접근
        self.cfg = TelegramConfig(
            enabled=bool(tg.get("enabled", False)),
            token=str(tg.get("token", "")),
            chat_id=str(tg.get("chat_id", "")),
        )
        self.base_url = f"https://api.telegram.org/bot{self.cfg.token}/sendMessage"

    def send(self, text: str) -> None:
        if not self.cfg.enabled:
            return

        payload = {
            "chat_id": self.cfg.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }

        # parse_mode는 마크다운 이스케이프 이슈가 귀찮으니 MVP에선 생략(안전)
        r = requests.post(self.base_url, json=payload, timeout=5)
        r.raise_for_status()
