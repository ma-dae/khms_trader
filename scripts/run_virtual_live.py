# scripts/run_virtual_live.py
from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Dict

import pandas as pd

from khms_trader.config import load_settings
from khms_trader.broker.korea_invest_api import KoreaInvestBroker
from khms_trader.broker.base import OrderRequest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _call_first(obj: Any, names: list[str], *args, **kwargs):
    for n in names:
        fn = getattr(obj, n, None)
        if callable(fn):
            return n, fn(*args, **kwargs)
    return None, None


def _now_kst_str() -> str:
    # 사용자 TZ가 Asia/Seoul이므로 단순 표기
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _is_market_open_kst() -> bool:
    # KRX 정규장: 09:00~15:30 (단순 버전; 공휴일/조기폐장 제외)
    t = datetime.now()
    if t.weekday() >= 5:  # 토/일
        return False
    hhmm = t.hour * 100 + t.minute
    return (900 <= hhmm <= 1530)


def _pick_latest_universe_csv() -> Optional[Path]:
    d = PROJECT_ROOT / "data" / "universe"
    if not d.exists():
        return None
    files = sorted(d.glob("kosdaq_*.csv"))
    return files[-1] if files else None


def _load_symbols_from_universe(limit: int = 20) -> list[str]:
    p = _pick_latest_universe_csv()
    if not p:
        return []
    df = pd.read_csv(p)
    # 흔한 컬럼명 후보: code, symbol, 종목코드 등
    for col in ["code", "symbol", "ticker", "종목코드"]:
        if col in df.columns:
            syms = [str(x).zfill(6) for x in df[col].dropna().astype(str).tolist()]
            return syms[:limit]
    # fallback: 첫 컬럼
    col0 = df.columns[0]
    syms = [str(x).zfill(6) for x in df[col0].dropna().astype(str).tolist()]
    return syms[:limit]


def _make_kis_virtual_broker(s: dict) -> KoreaInvestBroker:
    broker_cfg = s.get("broker") or {}
    provider = broker_cfg.get("provider")
    env = broker_cfg.get("env") or "virtual"
    if provider != "korea_invest":
        raise ValueError(f"run_virtual_live.py supports provider='korea_invest' only. got {provider}")
    if env != "virtual":
        raise ValueError(f"run_virtual_live.py is for VTS(virtual). got env={env}")

    creds = s["korea_invest"][env]

    base_url = (creds.get("base_url") or "").strip()
    if not base_url:
        base_url = "https://openapivts.koreainvestment.com:29443"

    return KoreaInvestBroker(
        app_key=creds["app_key"],
        app_secret=creds["app_secret"],
        account_no=creds["account_no"],
        account_product_code=(creds.get("account_product_code") or "01"),
        base_url=base_url,
        virtual=True,
    )


def _make_signal(strategy_obj: Any, symbol: str) -> str:
    """
    전략 객체가 있으면 전략에 위임.
    없거나 인터페이스가 다르면 HOLD.
    반환: BUY / SELL / HOLD
    """
    # 가능한 메서드 후보들
    for name in ["signal", "get_signal", "generate_signal", "decide", "decide_signal"]:
        fn = getattr(strategy_obj, name, None)
        if callable(fn):
            out = fn(symbol)
            if isinstance(out, str):
                out = out.upper().strip()
                return out if out in ("BUY", "SELL", "HOLD") else "HOLD"
    return "HOLD"


def _send_telegram(s: dict, text: str) -> None:
    tg = s.get("telegram") or {}
    if not tg.get("enabled"):
        return
    try:
        from khms_trader.notifications.telegram import TelegramNotifier  # 프로젝트에 맞춰 존재한다고 가정
        notifier = TelegramNotifier(token=tg["token"], chat_id=tg["chat_id"])
        notifier.send(text)
    except Exception as e:
        print(f"[WARN] telegram send failed: {e}")


def main() -> None:
    ap = argparse.ArgumentParser("Virtual live loop (single run) - signal -> order -> status -> report")
    ap.add_argument("--symbol", default=None, help="single symbol (e.g., 229200). If omitted, use universe csv.")
    ap.add_argument("--universe-limit", type=int, default=10, help="how many symbols from universe to scan")
    ap.add_argument("--qty", type=int, default=1, help="default order quantity")
    ap.add_argument("--price", type=float, default=None, help="limit price; None means market(if broker maps)")
    ap.add_argument("--place-order", action="store_true", help="actually place order (otherwise dry run)")
    ap.add_argument("--poll-seconds", type=int, default=15, help="seconds to poll order status")
    ap.add_argument("--poll-interval", type=float, default=3.0, help="poll interval seconds")
    ap.add_argument("--force", action="store_true", help="ignore market hours check")
    ap.add_argument("--auto-sell", action="store_true", help="auto sell after buy fill (restore position)")
    args = ap.parse_args()

    s = load_settings()
    api = _make_kis_virtual_broker(s)

    print(f"[{_now_kst_str()}] init OK: {api.__class__.__name__}")

    # 장 시간 체크(정규장만)
    if not args.force and not _is_market_open_kst():
        msg = f"[SKIP] market closed (KST). use --force to run anyway."
        print(msg)
        _send_telegram(s, msg)
        return

    cash = api.get_cash()
    pos = api.get_positions() if hasattr(api, "get_positions") else {}
    print(f"[STATE] cash={cash} positions={pos}")

    # 심볼 리스트
    if args.symbol:
        symbols = [str(args.symbol).zfill(6)]
    else:
        symbols = _load_symbols_from_universe(limit=args.universe_limit)
        if not symbols:
            raise RuntimeError("No symbols. Provide --symbol or add data/universe/kosdaq_*.csv")

    # 전략 로딩(있으면 사용, 없으면 HOLD로 처리)
    strategy_obj = None
    try:
        from khms_trader.strategies.hsms import HSMS  # 프로젝트에 따라 클래스명이 다를 수 있음
        strategy_obj = HSMS()
    except Exception:
        try:
            from khms_trader.strategies.hsms import HSMSStrategy
            strategy_obj = HSMSStrategy()
        except Exception:
            strategy_obj = None

    # 간단 루프: 첫 BUY 신호만 실행(데모/운영 안전)
    placed_any = False
    for sym in symbols:
        held = (pos or {}).get(sym, 0)
        sig = "HOLD" if strategy_obj is None else _make_signal(strategy_obj, sym)

        print(f"[SCAN] {sym} signal={sig} held={held}")

        if sig != "BUY":
            continue

        # 리스크 가드(초간단): 이미 보유면 중복매수 방지
        if held and held > 0:
            print(f"[SKIP] {sym} already held={held}")
            continue

        if not args.place_order:
            print(f"[DRYRUN] would BUY {sym} qty={args.qty} price={args.price}")
            placed_any = True
            break

        req = OrderRequest(symbol=sym, side="BUY", quantity=args.qty, price=args.price)
        resp = api.place_order(req)

        ok = getattr(resp, "ok", None)
        msg = getattr(resp, "message", "") or getattr(resp, "msg", "")
        order_id = getattr(resp, "order_id", None) or getattr(resp, "order_no", None)

        # 접수 성공 판정(주문번호 있으면 접수로 간주)
        accepted = (ok is True) or (order_id is not None and str(order_id).strip() != "")
        print(f"[ORDER] accepted={accepted} ok={ok} msg={msg} order_id={order_id}")

        _send_telegram(s, f"[VIRTUAL][ORDER] {sym} BUY qty={args.qty} price={args.price} accepted={accepted} order_id={order_id}\n{msg}")

        if not accepted:
            raise RuntimeError(f"Order rejected: {msg}")

        # 체결 상태 폴링(get_order_status가 있으면)
        if order_id and hasattr(api, "get_order_status"):
            deadline = time.time() + args.poll_seconds
            while time.time() < deadline:
                st = api.get_order_status(str(order_id))
                if isinstance(st, dict) and st.get("found"):
                    ord_qty = st.get("ord_qty")
                    filled = st.get("filled_qty")
                    unfilled = st.get("unfilled_qty")
                    avg_price = (st.get("record") or {}).get("avg_prvs")
                    print(f"  [FILL] {order_id} filled={filled}/{ord_qty} unfilled={unfilled} avg_price={avg_price}")
                    if filled is not None and ord_qty is not None and filled >= ord_qty:
                        print("  → fully filled")
                        break
                time.sleep(args.poll_interval)
        # --- AUTO SELL ---
        if args.auto_sell:
            print(f"[AUTO-SELL] placing SELL for {sym} qty={args.qty}")

            sell_req = OrderRequest(
                symbol=sym,
                side="SELL",
                quantity=args.qty,
                price=None,  # 시장가
            )

            sell_resp = api.place_order(sell_req)

            sell_ok = getattr(sell_resp, "ok", None)
            sell_msg = getattr(sell_resp, "message", "") or getattr(sell_resp, "msg", "")
            sell_order_id = getattr(sell_resp, "order_id", None) or getattr(sell_resp, "order_no", None)

            accepted = (sell_ok is True) or (sell_order_id is not None)
            print(f"[AUTO-SELL] accepted={accepted} order_id={sell_order_id} msg={sell_msg}")

            if not accepted:
                raise RuntimeError(f"AUTO-SELL rejected: {sell_msg}")

            # SELL 체결 확인
            if sell_order_id and hasattr(api, "get_order_status"):
                deadline = time.time() + args.poll_seconds
                while time.time() < deadline:
                    st = api.get_order_status(str(sell_order_id))
                    if isinstance(st, dict) and st.get("found"):
                        ord_qty = st.get("ord_qty")
                        filled = st.get("filled_qty")
                        avg_price = (st.get("record") or {}).get("avg_prvs")

                        print(f"  [SELL-FILL] filled={filled}/{ord_qty} avg_price={avg_price}")

                        if filled is not None and ord_qty is not None and filled >= ord_qty:
                            print("  → AUTO-SELL fully filled")
                            break
                    time.sleep(args.poll_interval)



        # 주문 후 최신 상태 출력
        cash2 = api.get_cash()
        pos2 = api.get_positions() if hasattr(api, "get_positions") else {}
        held2 = (pos2 or {}).get(sym, 0)
        print(f"[STATE_AFTER] cash={cash2} held({sym})={held2}")

        _send_telegram(s, f"[VIRTUAL][STATE] cash={cash2} held({sym})={held2}")
        placed_any = True
        break

    if not placed_any:
        msg = "[DONE] no actionable signal (or all skipped)."
        print(msg)
        _send_telegram(s, msg)


if __name__ == "__main__":
    main()
