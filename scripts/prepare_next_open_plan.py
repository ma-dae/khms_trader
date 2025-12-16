# scripts/prepare_next_open_plan.py
from __future__ import annotations

import argparse
import os
from pathlib import Path

from khms_trader.execution.runner import NextOpenConfig, prepare_next_open_plan
from khms_trader.notifications.telegram import TelegramNotifier


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _ensure_pythonpath() -> None:
    src = str(PROJECT_ROOT / "src")
    cur = os.environ.get("PYTHONPATH", "")
    if src not in cur.split(os.pathsep):
        os.environ["PYTHONPATH"] = src + (os.pathsep + cur if cur else "")


def main() -> None:
    ap = argparse.ArgumentParser("Prepare NEXT_OPEN plan (15:40 job) - manual runner")
    ap.add_argument("--universe-limit", type=int, default=200)
    ap.add_argument("--qty", type=int, default=1)
    ap.add_argument("--poll-seconds", type=int, default=15)
    ap.add_argument("--poll-interval", type=float, default=3.0)
    args = ap.parse_args()

    _ensure_pythonpath()

    tg = TelegramNotifier()
    try:
        tg.send(
            f"[MANUAL][PLAN][START] "
            f"universe_limit={args.universe_limit} qty={args.qty}"
        )
    except Exception:
        pass

    cfg = NextOpenConfig(
        universe_limit=args.universe_limit,
        qty=args.qty,
        poll_seconds=args.poll_seconds,
        poll_interval=args.poll_interval,
    )

    try:
        prepare_next_open_plan(cfg)
        try:
            tg.send("[MANUAL][PLAN][DONE] prepare_next_open_plan completed")
        except Exception:
            pass
    except Exception as e:
        try:
            tg.send(f"[MANUAL][PLAN][ERROR] {type(e).__name__}: {e}")
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
