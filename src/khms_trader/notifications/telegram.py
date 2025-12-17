from __future__ import annotations

import requests
import time
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
        print("[DEBUG] telegram enabled/token/chat_id:", self.cfg.enabled, bool(self.cfg.token), self.cfg.chat_id)

    def send(self, text: str) -> None:
        if not self.cfg.enabled:
            return

        payload = {
            "chat_id": self.cfg.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }


        last_err = None
        for attempt in range(3):
            try:
                r = self._session.post(self.base_url, json=payload, timeout=5)
                if not r.ok:
                    print(f"[WARN] telegram send failed: status={r.status_code} body={r.text}")
                r.raise_for_status()
                return
            except requests.exceptions.RequestException as e:
                last_err = e
                # 세션이 꼬였을 수 있으니 재생성
                self._session.close()
                self._session = requests.Session()
                time.sleep(0.5 * (attempt + 1))

        print(f"[WARN] telegram send failed: {last_err}")