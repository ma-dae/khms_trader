from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Optional, Dict

Side = Literal['BUY', 'SELL']

@dataclass
class OrderRequest:
    """
    주문 요청 정보.
    모의투자/실전 브로커 모두 이 구조를 사용한다.
    """

    symbol: str
    side: Side
    quantity: int
    price: Optional[float] = None  # None이면 시장가(실전 브로커에서 처리)


@dataclass
class OrderResult:
    """
    주문 결과 정보.
    """

    success: bool
    order_id: Optional[str] = None
    filled_quantity: int = 0
    avg_price: Optional[float] = None
    message: str = ""


class BaseBroker(ABC):
    """
    브로커 공통 인터페이스.

    PaperBroker, KoreaInvestBroker 모두 이 클래스를 상속해서 구현한다.
    """

    @abstractmethod
    def get_cash(self) -> float:
        """가용 현금 잔고 조회."""
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> Dict[str, int]:
        """현재 보유 종목과 수량 조회."""
        raise NotImplementedError

    @abstractmethod
    def get_position(self, symbol: str) -> int:
        """특정 종목 보유 수량 조회."""
        raise NotImplementedError

    @abstractmethod
    def place_order(self, req: OrderRequest) -> OrderResult:
        """주문 실행."""
        raise NotImplementedError