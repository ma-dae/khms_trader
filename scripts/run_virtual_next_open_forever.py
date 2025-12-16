# scripts/run_virtual_next_open_forever.py
from __future__ import annotations

import argparse
import os
from pathlib import Path
from datetime import datetime

from khms_trader.execution.scheduler import TimeOfDayScheduler, TimeOfDaySchedule
from khms_trader.execution.runner import NextOpenConfig, prepare_next_open_plan, execute_next_open_plan

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ensure_pythonpath() -> None:
    """
    scripts 실행 시 src 인식 안정화(Windows/Anaconda 환경 대비).
    """
    src_path = str(PROJECT_ROOT / "src")
    cur = os.environ.get("PYTHONPATH", "")
    if src_path not in cur.split(os.pathsep):
        os.environ["PYTHONPATH"] = src_path + (os.pathsep + cur if cur else "")


def main() -> None:
    ap = argparse.ArgumentParser("Run NEXT_OPEN virtual trading forever (plan@15:40, execute@09:01)")
    ap.add_argument(
        "--times",
        nargs="+",
        default=["09:01", "15:40"],
        help='times in HH:MM (default: 09:01 15:40). If you want only execute, set --times 09:01',
    )
    ap.add_argument("--universe-limit", type=int, default=200)
    ap.add_argument("--qty", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true", help="do not place orders (execute step)")
    ap.add_argument("--poll-seconds", type=int, default=15)
    ap.add_argument("--poll-interval", type=float, default=3.0)
    args = ap.parse_args()

    _ensure_pythonpath()

    cfg = NextOpenConfig(
        universe_limit=args.universe_limit,
        qty=args.qty,
        poll_seconds=args.poll_seconds,
        poll_interval=args.poll_interval,
    )

    times = list(args.times)

    def job(triggered_hhmm: str) -> None:
        # 정식 next_open: 15:40에 내일 plan 생성, 09:01에 plan 실행
        if triggered_hhmm == "15:40":
            print(f"[{_now()}] JOB: prepare_next_open_plan")
            prepare_next_open_plan(cfg)
        elif triggered_hhmm == "09:01":
            print(f"[{_now()}] JOB: execute_next_open_plan (dry_run={args.dry_run})")
            execute_next_open_plan(cfg, dry_run=args.dry_run)
        else:
            # times를 커스텀으로 넣었을 때도 안전하게
            print(f"[{_now()}] SKIP: no handler for trigger={triggered_hhmm}")

    lock_path = PROJECT_ROOT / "logs" / "next_open.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[{_now()}] next_open scheduler start | times={times} | lock={lock_path}")

    sched = TimeOfDayScheduler(
        schedule=TimeOfDaySchedule(times_hhmm=times),
        job=job,
        lock_path=lock_path,
    )
    sched.run_forever()


if __name__ == "__main__":
    main()
