# scripts/run_virtual_live_scheduler.py
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _build_env() -> dict:
    """
    Windows/Anaconda에서 scripts를 실행할 때 src 패키지 인식 문제 방지.
    """
    env = os.environ.copy()
    src_path = str(PROJECT_ROOT / "src")
    env["PYTHONPATH"] = src_path + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def main() -> None:
    ap = argparse.ArgumentParser("Run virtual live loop on a fixed interval")
    ap.add_argument("--interval", type=int, default=60, help="seconds between runs (e.g., 60, 300)")
    ap.add_argument("--align", action="store_true", help="align ticks to wall-clock interval boundaries")
    ap.add_argument("--symbol", default=None, help="single symbol (e.g., 229200)")
    ap.add_argument("--qty", type=int, default=1)
    ap.add_argument("--price", type=float, default=None)
    ap.add_argument("--place-order", action="store_true")
    ap.add_argument("--auto-sell", action="store_true")
    ap.add_argument("--force", action="store_true", help="ignore market hours check in run_virtual_live.py")
    args = ap.parse_args()

    base_cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "run_virtual_live.py")]

    if args.symbol:
        base_cmd += ["--symbol", args.symbol]
    base_cmd += ["--qty", str(args.qty)]

    if args.price is not None:
        base_cmd += ["--price", str(args.price)]

    if args.place_order:
        base_cmd += ["--place-order"]
    if args.auto_sell:
        base_cmd += ["--auto-sell"]
    if args.force:
        base_cmd += ["--force"]

    env = _build_env()

    print(f"[{_now()}] interval-scheduler start | interval={args.interval}s | cmd={' '.join(base_cmd)}")

    def _aligned_next_run(now: float, interval: int) -> float:
        base = (now // interval) * interval
        return base + interval

    next_run = _aligned_next_run(time.time(), args.interval) if args.align else time.time()

    while True:
        now = time.time()
        if now < next_run:
            time.sleep(max(0.2, next_run - now))
            continue

        print(f"\n[{_now()}] tick -> run_virtual_live.py")
        try:
            p = subprocess.run(base_cmd, env=env)
            if p.returncode != 0:
                print(f"[{_now()}] WARN: run returned code={p.returncode}")
        except KeyboardInterrupt:
            print(f"\n[{_now()}] scheduler stopped by user")
            break
        except Exception as e:
            print(f"[{_now()}] ERROR: {e}")

        next_run = _aligned_next_run(time.time(), args.interval) if args.align else (time.time() + args.interval)


if __name__ == "__main__":
    main()
