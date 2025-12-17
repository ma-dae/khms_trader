from khms_trader.config import load_settings
from khms_trader.notifications.telegram import TelegramNotifier

def main():
    s = load_settings()
    tg = s.get("telegram") or {}
    n = TelegramNotifier(str(tg.get("token","")), str(tg.get("chat_id","")))
    n.send("[KHMS] Telegram 연동 테스트 메시지")

if __name__ == "__main__":
    main()
