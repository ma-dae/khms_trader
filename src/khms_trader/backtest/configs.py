from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class BacktestConfig:
    """
    백테스트 엄밀성 옵션
    - fill_mode:
        * "close": 신호 발생 당일 종가 체결(비교용)
        * "next_open": 신호 발생 다음날 시가 체결(룩어헤드 방지 권장 기본)
    - fee_bps: 매수/매도 수수료(bps)
    - tax_bps: 매도 시 거래세(bps)
    - slippage_bps: 슬리피지(bps)
    """
    fill_mode: str = "next_open"
    fee_bps: float = 0.0
    tax_bps: float = 0.0
    slippage_bps: float = 0.0

    @property
    def fee_rate(self) -> float:
        return self.fee_bps / 10_000.0

    @property
    def tax_rate(self) -> float:
        return self.tax_bps / 10_000.0

    @property
    def slippage_rate(self) -> float:
        return self.slippage_bps / 10_000.0
