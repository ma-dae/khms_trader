from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional

from khms_trader.config import load_settings
from khms_trader.backtest.configs import BacktestConfig

def make_bt_config(settings: Optional[Dict[str, Any]] = None, *, fill_mode: Optional[str] = None) -> BacktestConfig:
    settings = settings or load_settings()
    trading = settings.get("trading") or {}

    cfg = BacktestConfig(
        fill_mode=str(trading.get("fill_mode", "next_open")),
        fee_bps=float(trading.get("fee_bps", 0.0)),
        tax_bps=float(trading.get("tax_bps", 0.0)),
        slippage_bps=float(trading.get("slippage_bps", 0.0)),
    )
    if fill_mode is not None:
        cfg = BacktestConfig(
            fill_mode=fill_mode,
            fee_bps=cfg.fee_bps,
            tax_bps=cfg.tax_bps,
            slippage_bps=cfg.slippage_bps,
        )
    return cfg

def make_test_cases(settings: Optional[Dict[str, Any]] = None) -> List[Tuple[str, BacktestConfig]]:
    base = make_bt_config(settings=settings)
    return [
        ("A_next_open_cost_OFF", BacktestConfig(fill_mode="next_open", fee_bps=0.0, tax_bps=0.0, slippage_bps=0.0)),
        ("B_next_open_cost_ON",  BacktestConfig(fill_mode="next_open", fee_bps=base.fee_bps, tax_bps=base.tax_bps, slippage_bps=base.slippage_bps)),
        ("C_close_cost_ON",      BacktestConfig(fill_mode="close",     fee_bps=base.fee_bps, tax_bps=base.tax_bps, slippage_bps=base.slippage_bps)),
    ]
