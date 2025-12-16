# scripts/run_virtual_tick_forever.py
from __future__ import annotations

import argparse
from pathlib import Path

from khms_trader.execution.scheduler import IntervalScheduler, IntervalSchedule
from khms_trader.execution.runner import run_virtual_tick, LiveRunConfig

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def main() -> None:
    ap = argparse.ArgumentParser("Run virtual tick forever with IntervalScheduler")
    ap.add_argument("--interval", type=int, default=300)
    ap.add_argument("--universe-limit", type=int, default=50)
    ap.add_argument("--qty", type=int, default=1)
    ap.add_argument("--price", type=float, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = LiveRunConfig(
        universe_limit=args.universe_limit,
        qty=args.qty,
        price=args.price,
        place_order=(not args.dry_run),
    )

    lock_path = PROJECT_ROOT / "logs" / "virtual_tick.lock"

    sched = IntervalScheduler(
        schedule=IntervalSchedule(interval_sec=args.interval, align_to_interval=True),
        job=lambda: run_virtual_tick(cfg),
        lock_path=lock_path,
    )
    sched.run_forever()

if __name__ == "__main__":
    main()
