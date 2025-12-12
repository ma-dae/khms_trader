from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from .base import BaseBroker, OrderRequest, OrderResult


@dataclass
class PaperBroker(BaseBroker):
    """
    모의투자용 브로커.

    - 모든 주문은 지정가로 100% 체결된다고 가정
    - 현금/포지션만 메모리 상에서 관리
    """

    cash: float = 100_000_000.0  # 초기 모의투자 자본 (예: 1억)
    positions: Dict[str, int] = field(default_factory=dict)
    _order_seq: int = 0

    def _next_order_id(self) -> str:
        self._order_seq += 1
        return f"PB-{self._order_seq:08d}"

    # --- 인터페이스 구현 ---

    def get_cash(self) -> float:
        return self.cash

    def get_positions(self) -> Dict[str, int]:
        return dict(self.positions)

    def get_position(self, symbol: str) -> int:
        return self.positions.get(symbol, 0)

    def place_order(self, req: OrderRequest) -> OrderResult:
        """
        시장/지정가 구분 없이, 요청된 price에 전량 체결된다고 가정.

        runner 쪽에서 현재가(또는 종가)를 price에 넣어서 넘겨주는 형태로 사용.
        """
        if req.quantity <= 0:
            return OrderResult(
                success=False,
                message="quantity must be positive",
            )

        if req.price is None:
            return OrderResult(
                success=False,
                message="PaperBroker: price must be provided for simulation",
            )

        cost = req.price * req.quantity

        if req.side == "BUY":
            # 현금 부족 체크
            if self.cash < cost:
                return OrderResult(
                    success=False,
                    message=f"insufficient cash: required={cost}, cash={self.cash}",
                )
            # 매수 체결
            self.cash -= cost
            self.positions[req.symbol] = self.positions.get(req.symbol, 0) + req.quantity

        elif req.side == "SELL":
            pos = self.positions.get(req.symbol, 0)
            if pos < req.quantity:
                return OrderResult(
                    success=False,
                    message=f"insufficient position: have={pos}, try_sell={req.quantity}",
                )
            # 매도 체결
            self.cash += cost
            new_pos = pos - req.quantity
            if new_pos == 0:
                self.positions.pop(req.symbol, None)
            else:
                self.positions[req.symbol] = new_pos

        order_id = self._next_order_id()
        return OrderResult(
            success=True,
            order_id=order_id,
            filled_quantity=req.quantity,
            avg_price=req.price,
            message="filled (paper)",
        )
