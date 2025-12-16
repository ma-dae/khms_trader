# src/khms_trader/broker/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class OrderRequest:
    """
    주문 요청 모델 (브로커 공통)
    - symbol: 종목코드 (예: "229200")
    - side: "BUY" | "SELL"
    - quantity: 주문수량 (정수)
    - price: 주문가격 (지정가). 시장가면 None 또는 0 사용(브로커 구현에서 해석)
    """
    symbol: str
    side: str
    quantity: int
    price: Optional[float] = None


@dataclass
class OrderResult:
    """
    주문 결과 모델 (브로커 공통)
    - success: 성공 여부
    - message: 메시지
    - order_id: 주문번호(있으면)
    - raw: 브로커 원본 응답(디버깅용)
    """
    success: bool
    message: str = ""
    order_id: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


class BaseBroker(ABC):
    """
    브로커 공통 인터페이스.
    PaperBroker / KoreaInvestBroker 등이 이를 구현.
    """

    @abstractmethod
    def get_cash(self) -> float:
        """현재 예수금(또는 사용 가능 현금)"""
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> Dict[str, int]:
        """보유 종목 수량 딕셔너리: {symbol: qty}"""
        raise NotImplementedError

    def get_position(self, symbol: str) -> int:
        """특정 종목 보유 수량"""
        return int(self.get_positions().get(symbol, 0))

    @abstractmethod
    def place_order(self, req: OrderRequest) -> OrderResult:
        """주문 실행"""
        raise NotImplementedError
