# scripts/execute_next_open_plan.py
from __future__ import annotations

import argparse
import os
from pathlib import Path

from khms_trader.execution.runner import NextOpenConfig, execute_next_open_plan
from khms_trader.notifications.telegram import TelegramNotifier


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _ensure_pythonpath() -> None:
    src = str(PROJECT_ROOT / "src")
    cur = os.environ.get("PYTHONPATH", "")
    if src not in cur.split(os.pathsep):
        os.environ["PYTHONPATH"] = src + (os.pathsep + cur if cur else "")


def main() -> None:
    ap = argparse.ArgumentParser("Execute NEXT_OPEN plan (09:01 job) - manual runner")
    ap.add_argument("--universe-limit", type=int, default=200)
    ap.add_argument("--qty", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--poll-seconds", type=int, default=15)
    ap.add_argument("--poll-interval", type=float, default=3.0)
    args = ap.parse_args()

    _ensure_pythonpath()

    tg = TelegramNotifier()
    try:
        tg.send(
            f"[MANUAL][EXEC][START] "
            f"dry_run={args.dry_run} qty={args.qty}"
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
        execute_next_open_plan(cfg, dry_run=args.dry_run)
        try:
            tg.send("[MANUAL][EXEC][DONE] execute_next_open_plan completed")
        except Exception:
            pass
    except Exception as e:
        try:
            tg.send(f"[MANUAL][EXEC][ERROR] {type(e).__name__}: {e}")
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
