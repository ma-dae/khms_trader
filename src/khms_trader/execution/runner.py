from __future__ import annotations

from typing import List

from ..broker import get_broker        
from ..broker.base import OrderRequest
from ..data.loader import load_symbol_ohlcv_with_foreign
from ..data.screener import screen_top_by_volume_volatility
from ..execution.risk import calc_position_size_by_ratio
from ..strategies.hsms import HSMSStrategy


def run_paper_trading_auto_universe() -> None:
    # 1) 자동 스크리닝으로 심볼 리스트 뽑기
    symbols = screen_top_by_volume_volatility(
        lookback_days=20,
        top_n=20,
        min_price=5_000.0,
        min_avg_volume=50_000.0,
    )

    if not symbols:
        print("[runner] 스크리너에서 선택된 심볼이 없습니다. 종료합니다.")
        return

    # 2) setting.yaml에 따른 브로커 생성 (paper, virtual, real)
    broker = get_broker()
    strategy = HSMSStrategy()

    print("=== Paper Trading (Auto Universe) Start ===")
    print(f"초기 현금: {broker.get_cash():,.0f}원\n")

    for symbol in symbols:
        print(f"[{symbol}] 종목 처리 중...")

        df = load_symbol_ohlcv_with_foreign(symbol)
        if df.empty:
            print(f"  -> 데이터 없음, 스킵")
            continue

        sig = strategy.generate_signals(df)
        last = sig.iloc[-1]
        last_date = sig.index[-1]

        price = float(last["close"])
        has_pos = broker.get_position(symbol) > 0

        buy_signal = bool(last["buy_signal"])
        sell_signal = bool(last["sell_signal"])

        print(f"  날짜: {last_date.date()}, 종가: {price:,.2f}")
        print(f"  buy_signal={buy_signal}, sell_signal={sell_signal}, 보유수량={broker.get_position(symbol)}")

        if not has_pos and buy_signal:
            cash = broker.get_cash()
            qty = calc_position_size_by_ratio(cash, price, ratio=0.1)
            if qty > 0:
                req = OrderRequest(symbol=symbol, side="BUY", quantity=qty, price=price)
                res = broker.place_order(req)
                print(f"  -> BUY {qty} @ {price:,.2f}, success={res.success}, msg={res.message}")
            else:
                print("  -> 매수 수량 0 (현금 부족 또는 가격 이상)")

        elif has_pos and sell_signal:
            pos = broker.get_position(symbol)
            req = OrderRequest(symbol=symbol, side="SELL", quantity=pos, price=price)
            res = broker.place_order(req)
            print(f"  -> SELL {pos} @ {price:,.2f}, success={res.success}, msg={res.message}")
        else:
            print("  -> 아무 행동도 하지 않음")

        print()

    print("=== Paper Trading (Auto Universe) End ===")
    print(f"최종 현금: {broker.get_cash():,.0f}원")
    print(f"최종 포지션: {broker.get_positions()}")
