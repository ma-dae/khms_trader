# paper 용 
from __future__ import annotations

from typing import Optional

from khms_trader.config import load_settings
from khms_trader.broker.base import OrderRequest
from khms_trader.broker.factory import make_broker
from khms_trader.data.loader import load_symbol_ohlcv_with_foreign
from khms_trader.data.screener import screen_top_by_volume_volatility
from khms_trader.execution.risk import calc_position_size_by_ratio
from khms_trader.strategies.hsms import HSMSStrategy
from khms_trader.notifications.telegram import TelegramNotifier
# 텔레그램 모듈 경로는 프로젝트 내부 기준으로 통일
from khms_trader.notifications.telegram import TelegramNotifier


def _make_notifier(settings: dict) -> Optional[TelegramNotifier]:
    tg_cfg = (settings.get("telegram") or {})
    enabled = bool(tg_cfg.get("enabled", False))  # ✅ enable -> enabled로 통일 권장
    if not enabled:
        return None
    return TelegramNotifier(
        token=str(tg_cfg.get("token", "")),
        chat_id=str(tg_cfg.get("chat_id", "")),
    )


def run_paper_trading_auto_universe() -> None:
    """
    설정(setting+secrets 병합) 기반으로 broker를 만들고,
    스크리너 → 전략 시그널 → 주문(또는 페이퍼 주문)을 수행.
    """
    settings = load_settings()
    notifier = _make_notifier(settings)

    # 1) 자동 스크리닝으로 심볼 리스트 뽑기
    symbols = screen_top_by_volume_volatility(
        lookback_days=20,
        top_n=20,
        min_price=5_000.0,
        min_avg_volume=50_000.0,
    )

    if not symbols:
        msg = "[runner] 스크리너에서 선택된 심볼이 없습니다. 종료합니다."
        print(msg)
        if notifier:
            notifier.send(msg)
        return

    # 2) setting.yaml에 따른 브로커 생성 (paper / korea_invest_virtual ...)
    broker = make_broker()
    strategy = HSMSStrategy()

    start_msg = "=== LIVE/PAPER Trading (Auto Universe) Start ==="
    print(start_msg)
    if notifier:
        notifier.send(start_msg)

    try:
        cash0 = broker.get_cash()
        print(f"초기 현금: {cash0:,.0f}원\n")
        if notifier:
            notifier.send(f"[START] cash={cash0:,.0f} KRW, symbols={len(symbols)}")
    except Exception as e:
        print(f"[runner] 초기 현금 조회 실패: {e}")
        if notifier:
            notifier.send(f"[ERROR] 초기 현금 조회 실패: {e}")
        return

    for symbol in symbols:
        try:
            print(f"[{symbol}] 종목 처리 중...")

            df = load_symbol_ohlcv_with_foreign(symbol)
            if df is None or df.empty:
                print("  -> 데이터 없음, 스킵")
                continue

            sig = strategy.generate_signals(df)
            last = sig.iloc[-1]
            # loader가 date index면 그대로, 아니면 date 컬럼 처리 필요할 수 있음
            last_date = sig.index[-1] if hasattr(sig.index, "__len__") else None

            price = float(last["close"])
            pos_qty = int(broker.get_position(symbol) or 0)
            has_pos = pos_qty > 0

            buy_signal = bool(last.get("buy_signal", False))
            sell_signal = bool(last.get("sell_signal", False))

            if last_date is not None:
                print(f"  날짜: {getattr(last_date, 'date', lambda: last_date)()}, 종가: {price:,.2f}")
            else:
                print(f"  종가: {price:,.2f}")

            print(f"  buy_signal={buy_signal}, sell_signal={sell_signal}, 보유수량={pos_qty}")

            # ---- 매수 ----
            if (not has_pos) and buy_signal:
                cash = float(broker.get_cash())
                qty = int(calc_position_size_by_ratio(cash, price, ratio=0.1))

                if qty <= 0:
                    print("  -> 매수 수량 0 (현금 부족 또는 가격 이상)")
                    continue

                # OrderRequest 필드명이 (quantity)인지 (qty)인지 프로젝트에 따라 다를 수 있음.
                # 여기선 quantity를 쓰되, base.py가 qty를 쓰면 아래 한 줄만 바꾸면 됨.
                req = OrderRequest(symbol=symbol, side="BUY", quantity=qty, price=price)
                res = broker.place_order(req)

                msg = f"  -> BUY {qty} @ {price:,.2f}, success={getattr(res, 'success', None)}, msg={getattr(res, 'message', '')}"
                print(msg)
                if notifier:
                    notifier.send(f"[BUY] {symbol} qty={qty} price={price:,.2f} success={getattr(res, 'success', None)}")

            # ---- 매도 ----
            elif has_pos and sell_signal:
                req = OrderRequest(symbol=symbol, side="SELL", quantity=pos_qty, price=price)
                res = broker.place_order(req)

                msg = f"  -> SELL {pos_qty} @ {price:,.2f}, success={getattr(res, 'success', None)}, msg={getattr(res, 'message', '')}"
                print(msg)
                if notifier:
                    notifier.send(f"[SELL] {symbol} qty={pos_qty} price={price:,.2f} success={getattr(res, 'success', None)}")

            else:
                print("  -> 아무 행동도 하지 않음")

            print()

        except Exception as e:
            print(f"[runner][SKIP] symbol={symbol} err={e}")
            if notifier:
                notifier.send(f"[SKIP] {symbol} err={e}")

    # 종료 요약
    try:
        cash1 = broker.get_cash()
        pos = broker.get_positions()
        end_msg = "=== LIVE/PAPER Trading (Auto Universe) End ==="
        print(end_msg)
        print(f"최종 현금: {cash1:,.0f}원")
        print(f"최종 포지션: {pos}")
        if notifier:
            notifier.send(f"[END] cash={cash1:,.0f} KRW positions={len(pos)}")
    except Exception as e:
        print(f"[runner] 종료 요약 조회 실패: {e}")
        if notifier:
            notifier.send(f"[ERROR] 종료 요약 조회 실패: {e}")


# src/khms_trader/execution/runner.py 
# virtual용 
# src/khms_trader/execution/runner.py

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import pandas as pd

from khms_trader.config import load_settings
from khms_trader.broker.factory import make_broker
from khms_trader.broker.base import OrderRequest
from khms_trader.utils.time_utils import is_trading_day
from khms_trader.data.universe_kosdaq import get_kosdaq_universe_df
from khms_trader.data.loader import load_symbol_ohlcv_with_foreign
from khms_trader.strategies.hsms import HSMS2Strategy

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PLANS_DIR = PROJECT_ROOT / "plans"
PLANS_DIR.mkdir(parents=True, exist_ok=True)

REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
EVENTS_PATH = REPORTS_DIR / "live_events.jsonl"

# -----------------------------
# Date/Path helpers
# -----------------------------
def _today_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")


def _universe_path_for_today() -> Path:
    return PROJECT_ROOT / "data" / "universe" / f"kosdaq_{_today_yyyymmdd()}.csv"


def _plan_path_for_trading_day(yyyymmdd: str) -> Path:
    # 다음날(개장 직후) 실행할 plan
    return PLANS_DIR / f"next_open_plan_{yyyymmdd}.json"


def _next_trading_day_yyyymmdd() -> str:
    # 주말/공휴일 스킵해서 다음 거래일 찾기
    dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    while True:
        dt = dt + pd.Timedelta(days=1)
        if is_trading_day(dt):
            return dt.strftime("%Y%m%d")

# -----------------------------
# Telegram
# -----------------------------
def _tg() -> TelegramNotifier:
    """
    TelegramNotifier는 내부에서 load_settings()를 사용하므로
    runner에서는 그냥 생성해서 쓰면 됨.
    """
    return TelegramNotifier()


def _tg_send(tg: TelegramNotifier, msg: str) -> None:
    """
    텔레그램 실패가 매매 엔진을 죽이지 않게 보호.
    """
    try:
        tg.send(msg)
    except Exception:
        pass


# -----------------------------
# Dashboard
# -----------------------------

def _write_event(event: Dict[str, Any]) -> None:
    """
    Append-only JSONL event logger.
    실패해도 매매 엔진을 죽이지 않음.
    """
    try:
        event = dict(event)
        event.setdefault("ts", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(EVENTS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass

# -----------------------------
# Universe
# -----------------------------
def ensure_today_universe() -> Optional[Path]:
    """
    오늘이 거래일이면 오늘 universe가 있는지 확인하고,
    없으면 생성한다. (주말/공휴일은 None)
    """
    if not is_trading_day():
        print("[UNIVERSE] Today is not a trading day. Skip universe generation.")
        return None

    upath = _universe_path_for_today()
    upath.parent.mkdir(parents=True, exist_ok=True)

    if upath.exists():
        print(f"[UNIVERSE] Use existing universe: {upath.name}")
        return upath

    print(f"[UNIVERSE] Creating today's universe: {upath.name}")
    # 네 프로젝트 함수명에 맞춰 연결
    get_kosdaq_universe_df(output_path=upath)
    return upath


def _load_symbols_from_universe(path: Path, limit: int) -> List[str]:
    df = pd.read_csv(path)
    col = "code" if "code" in df.columns else df.columns[0]
    return [str(x).zfill(6) for x in df[col].dropna().astype(str).tolist()][:limit]


# -----------------------------
# NEXT_OPEN: Plan -> Execute
# -----------------------------
@dataclass
class NextOpenConfig:
    universe_limit: int = 200
    qty: int = 1
    # 주문 후 체결 확인(짧게)
    poll_seconds: int = 15
    poll_interval: float = 3.0


def prepare_next_open_plan(cfg: NextOpenConfig) -> Optional[Path]:
    """
    [15:40 실행 권장]
    - 전일(오늘) close 기준으로 HSMS2 신호 생성
    - 내일(다음 거래일) open에 실행할 plan 저장

    Plan에는 BUY 후보와 SELL 후보를 저장하되,
    실행 시점에 보유여부/중복 등을 한 번 더 필터링한다.
    """
    _write_event({"type": "PLAN_START", "mode": "next_open", "universe_limit": cfg.universe_limit})

    try:
        if not is_trading_day():
            print("[PLAN] not trading day -> skip")
            _write_event({"type": "PLAN_SKIP", "mode": "next_open", "reason": "not_trading_day"})
            return None

        upath = ensure_today_universe()
        if upath is None:
            print("[PLAN] universe missing -> skip")
            _write_event({"type": "PLAN_SKIP", "mode": "next_open", "reason": "universe_missing"})
            return None

        _write_event({"type": "PLAN_UNIVERSE", "mode": "next_open", "universe_file": upath.name})

        symbols = _load_symbols_from_universe(upath, limit=cfg.universe_limit)
        _write_event({"type": "PLAN_SYMBOLS", "mode": "next_open", "symbols_count": len(symbols)})

        strat = HSMS2Strategy()

        buy_list: List[str] = []
        sell_list: List[str] = []
        errors: Dict[str, str] = {}

        for sym in symbols:
            try:
                df = load_symbol_ohlcv_with_foreign(sym)
                if df is None or df.empty:
                    continue

                sig_df = strat.generate_signals(df)
                if sig_df is None or sig_df.empty:
                    continue

                last = sig_df.iloc[-1]
                if bool(last.get("buy_signal", False)):
                    buy_list.append(sym)
                if bool(last.get("sell_signal", False)):
                    sell_list.append(sym)

            except Exception as e:
                errors[sym] = str(e)

        next_day = _next_trading_day_yyyymmdd()
        plan_path = _plan_path_for_trading_day(next_day)

        plan = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "fill_mode": "next_open",
            "for_trading_day": next_day,
            "universe_file": upath.name,
            "buy": buy_list,
            "sell": sell_list,
            "errors": errors,
        }
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"[PLAN] saved {plan_path.name} | buy={len(buy_list)} sell={len(sell_list)} err={len(errors)}")

        _write_event({
            "type": "PLAN_DONE",
            "mode": "next_open",
            "for_trading_day": next_day,
            "universe_file": upath.name,
            "plan_file": plan_path.name,
            "buy_count": len(buy_list),
            "sell_count": len(sell_list),
            "error_count": len(errors),
        })

        if errors:
            # 너무 길어질 수 있어 샘플만 남김
            top3 = list(errors.items())[:3]
            sample = " | ".join([f"{s}:{m[:60]}" for s, m in top3])
            _write_event({"type": "PLAN_WARN", "mode": "next_open", "error_count": len(errors), "sample": sample})

        return plan_path

    except Exception as e:
        _write_event({"type": "ERROR", "stage": "PLAN", "mode": "next_open", "error": f"{type(e).__name__}: {e}"})
        raise



def execute_next_open_plan(cfg: NextOpenConfig, dry_run: bool = False) -> None:
    """
    [09:01 실행 권장]
    - 오늘자 plan 파일을 읽어 open에 BUY/SELL 집행
    - 실제 집행 전에 보유 여부/중복 매수 등을 브로커 포지션으로 필터링
    """
    _write_event({
        "type": "EXEC_START",
        "mode": "next_open",
        "dry_run": dry_run,
        "qty": cfg.qty,
    })

    try:
        if not is_trading_day():
            print("[EXEC] not trading day -> skip")
            _write_event({"type": "EXEC_SKIP", "mode": "next_open", "reason": "not_trading_day"})
            return

        today = _today_yyyymmdd()
        plan_path = _plan_path_for_trading_day(today)
        if not plan_path.exists():
            print(f"[EXEC] plan not found: {plan_path.name}")
            _write_event({
                "type": "EXEC_SKIP",
                "mode": "next_open",
                "reason": "plan_missing",
                "plan_file": plan_path.name,
            })
            return

        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        buy_list = [str(x).zfill(6) for x in (plan.get("buy") or [])]
        sell_list = [str(x).zfill(6) for x in (plan.get("sell") or [])]

        broker = make_broker()
        positions: Dict[str, int] = broker.get_positions() if hasattr(broker, "get_positions") else {}

        _write_event({
            "type": "EXEC_PLAN",
            "mode": "next_open",
            "plan_file": plan_path.name,
            "buy_count": len(buy_list),
            "sell_count": len(sell_list),
            "positions_count": len(positions),
        })

        # ----------------
        # SELL
        # ----------------
        for sym in sell_list:
            held = int(positions.get(sym, 0))
            if held <= 0:
                continue

            if dry_run:
                print(f"[DRYRUN][SELL] {sym} qty={held}")
                _write_event({
                    "type": "ORDER_SUBMIT",
                    "mode": "next_open",
                    "side": "SELL",
                    "symbol": sym,
                    "qty": held,
                    "dry_run": True,
                })
                continue

            req = OrderRequest(symbol=sym, side="SELL", quantity=held, price=None)
            res = broker.place_order(req)
            order_id = getattr(res, "order_id", None) or getattr(res, "order_no", None)
            msg = getattr(res, "message", "") or getattr(res, "msg", "")

            print(f"[SELL] {sym} qty={held} order_id={order_id} msg={msg}")

            _write_event({
                "type": "ORDER_SUBMIT",
                "mode": "next_open",
                "side": "SELL",
                "symbol": sym,
                "qty": held,
                "order_id": str(order_id) if order_id else None,
                "message": msg,
                "dry_run": False,
            })

            # 체결 폴링 (최종 체결만 기록)
            if order_id and hasattr(broker, "get_order_status"):
                deadline = time.time() + cfg.poll_seconds
                while time.time() < deadline:
                    st = broker.get_order_status(str(order_id))
                    if isinstance(st, dict) and st.get("found"):
                        ord_qty = st.get("ord_qty")
                        filled = st.get("filled_qty")
                        avg_price = (st.get("record") or {}).get("avg_prvs")
                        if filled is not None and ord_qty is not None and filled >= ord_qty:
                            _write_event({
                                "type": "FILL_DONE",
                                "mode": "next_open",
                                "side": "SELL",
                                "symbol": sym,
                                "order_id": str(order_id),
                                "filled": int(filled),
                                "ord_qty": int(ord_qty),
                                "avg_price": avg_price,
                            })
                            break
                    time.sleep(cfg.poll_interval)

        # ----------------
        # BUY
        # ----------------
        for sym in buy_list:
            held = int(positions.get(sym, 0))
            if held > 0:
                continue

            if dry_run:
                print(f"[DRYRUN][BUY] {sym} qty={cfg.qty}")
                _write_event({
                    "type": "ORDER_SUBMIT",
                    "mode": "next_open",
                    "side": "BUY",
                    "symbol": sym,
                    "qty": cfg.qty,
                    "dry_run": True,
                })
                continue

            req = OrderRequest(symbol=sym, side="BUY", quantity=cfg.qty, price=None)
            res = broker.place_order(req)
            order_id = getattr(res, "order_id", None) or getattr(res, "order_no", None)
            msg = getattr(res, "message", "") or getattr(res, "msg", "")

            print(f"[BUY] {sym} qty={cfg.qty} order_id={order_id} msg={msg}")

            _write_event({
                "type": "ORDER_SUBMIT",
                "mode": "next_open",
                "side": "BUY",
                "symbol": sym,
                "qty": cfg.qty,
                "order_id": str(order_id) if order_id else None,
                "message": msg,
                "dry_run": False,
            })

            if order_id and hasattr(broker, "get_order_status"):
                deadline = time.time() + cfg.poll_seconds
                while time.time() < deadline:
                    st = broker.get_order_status(str(order_id))
                    if isinstance(st, dict) and st.get("found"):
                        ord_qty = st.get("ord_qty")
                        filled = st.get("filled_qty")
                        avg_price = (st.get("record") or {}).get("avg_prvs")
                        if filled is not None and ord_qty is not None and filled >= ord_qty:
                            _write_event({
                                "type": "FILL_DONE",
                                "mode": "next_open",
                                "side": "BUY",
                                "symbol": sym,
                                "order_id": str(order_id),
                                "filled": int(filled),
                                "ord_qty": int(ord_qty),
                                "avg_price": avg_price,
                            })
                            break
                    time.sleep(cfg.poll_interval)

        # 종료 요약
        try:
            cash = broker.get_cash()
            pos = broker.get_positions() if hasattr(broker, "get_positions") else {}
            _write_event({
                "type": "EXEC_DONE",
                "mode": "next_open",
                "dry_run": dry_run,
                "cash": cash,
                "positions_count": len(pos),
            })
        except Exception:
            _write_event({
                "type": "EXEC_DONE",
                "mode": "next_open",
                "dry_run": dry_run,
                "summary": "partial",
            })

    except Exception as e:
        _write_event({
            "type": "ERROR",
            "stage": "EXEC",
            "mode": "next_open",
            "error": f"{type(e).__name__}: {e}",
        })
        raise
