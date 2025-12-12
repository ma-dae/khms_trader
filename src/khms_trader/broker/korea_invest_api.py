from __future__ import annotations

from typing import Dict, Optional

from .base import BaseBroker, OrderRequest, OrderResult


class KoreaInvestBroker(BaseBroker):
    """
    한국투자증권 API 연동용 브로커 스켈레톤.

    virtual=True  -> 모의투자
    virtual=False -> 실거래
    """

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        account_no: str,
        virtual: bool = True,
    ) -> None:
        self.app_key = app_key
        self.app_secret = app_secret
        self.account_no = account_no
        self.virtual = virtual

        # TODO: 나중에 토큰 발급 / 세션 초기화 구현
        self._access_token: Optional[str] = None

    # --- BaseBroker 인터페이스 구현 ---

    def get_cash(self) -> float:
        # TODO: 한국투자 API에서 예수금 조회
        raise NotImplementedError("KoreaInvestBroker.get_cash: not implemented yet")

    def get_positions(self) -> Dict[str, int]:
        # TODO: 보유 종목 조회 API 연동
        raise NotImplementedError("KoreaInvestBroker.get_positions: not implemented yet")

    def get_position(self, symbol: str) -> int:
        # TODO: 특정 종목만 필터링
        raise NotImplementedError("KoreaInvestBroker.get_position: not implemented yet")

    def place_order(self, req: OrderRequest) -> OrderResult:
        # TODO: 주문 API 연동 (매수/매도)
        raise NotImplementedError("KoreaInvestBroker.place_order: not implemented yet")
