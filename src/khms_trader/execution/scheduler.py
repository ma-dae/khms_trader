# src/khms_trader/execution/scheduler.py
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional, List, Tuple

try:
    # Python 3.9+ (3.11 OK)
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore


# -----------------------------
# Lock (single instance)
# -----------------------------
class SingleInstanceLock:
    """
    아주 단순한 락: lock 파일을 만들어 중복 실행 방지.
    비정상 종료 시 lock 파일이 남을 수 있으므로,
    그 경우 사용자가 lock 파일을 삭제해야 함.
    """

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self._acquired = False

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if self.lock_path.exists():
            raise RuntimeError(
                f"Lock exists: {self.lock_path}. Another instance may be running, "
                f"or the previous run crashed. If you are sure no instance is running, "
                f"delete the lock file."
            )
        self.lock_path.write_text(str(os.getpid()), encoding="utf-8")
        self._acquired = True

    def release(self) -> None:
        if self._acquired and self.lock_path.exists():
            try:
                self.lock_path.unlink()
            except Exception:
                pass
        self._acquired = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# -----------------------------
# Interval scheduler
# -----------------------------
@dataclass
class IntervalSchedule:
    interval_sec: int = 60
    align_to_interval: bool = True  # True면 "벽시계 기준"으로 정렬(드리프트 최소)


class IntervalScheduler:
    def __init__(
        self,
        schedule: IntervalSchedule,
        job: Callable[[], None],
        lock_path: Optional[Path] = None,
        on_error_sleep_sec: float = 1.0,
    ):
        self.schedule = schedule
        self.job = job
        self.on_error_sleep_sec = on_error_sleep_sec
        self.lock_path = lock_path

    def _aligned_next_run(self, now: float) -> float:
        """
        벽시계 기준 정렬:
        예) interval=300이면 09:00, 09:05, 09:10 ... 에 맞춰 실행되도록 계산
        """
        interval = float(self.schedule.interval_sec)
        base = (now // interval) * interval
        return base + interval

    def run_forever(self) -> None:
        lock = SingleInstanceLock(self.lock_path) if self.lock_path else None

        def _loop() -> None:
            print(f"[{_now_str()}] interval-scheduler start | interval={self.schedule.interval_sec}s")
            next_run = self._aligned_next_run(time.time()) if self.schedule.align_to_interval else time.time()

            while True:
                now = time.time()
                if now < next_run:
                    time.sleep(max(0.2, next_run - now))
                    continue

                try:
                    print(f"\n[{_now_str()}] tick")
                    self.job()
                except KeyboardInterrupt:
                    print(f"\n[{_now_str()}] scheduler stopped by user")
                    break
                except Exception as e:
                    print(f"[{_now_str()}] ERROR in job: {e}")
                    time.sleep(self.on_error_sleep_sec)

                if self.schedule.align_to_interval:
                    next_run = self._aligned_next_run(time.time())
                else:
                    next_run += self.schedule.interval_sec

        if lock:
            with lock:
                _loop()
        else:
            _loop()


# -----------------------------
# Time-of-day scheduler
# -----------------------------
@dataclass
class TimeOfDaySchedule:
    times_hhmm: List[str]          # 예: ["09:01", "15:40"]
    timezone_name: str = "Asia/Seoul"


def _parse_hhmm(hhmm: str) -> Tuple[int, int]:
    if ":" not in hhmm:
        raise ValueError(f"Invalid time format: {hhmm}. expected HH:MM")
    hh_s, mm_s = hhmm.split(":", 1)
    hh = int(hh_s)
    mm = int(mm_s)
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError(f"Invalid time value: {hhmm}. expected 00:00..23:59")
    return hh, mm


def _tz_now(tz_name: str) -> datetime:
    if ZoneInfo is None:
        # fallback: 로컬 시간
        return datetime.now()
    return datetime.now(ZoneInfo(tz_name))


def _next_run_dt(times_hhmm: List[str], tz_name: str) -> datetime:
    """
    tz 기준으로, 다음 실행 시각(datetime)을 계산
    """
    now = _tz_now(tz_name)
    candidates: List[datetime] = []
    for t in times_hhmm:
        hh, mm = _parse_hhmm(t)
        dt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if dt <= now:
            dt = dt + timedelta(days=1)
        candidates.append(dt)
    return min(candidates)


class TimeOfDayScheduler:
    def __init__(
        self,
        schedule: TimeOfDaySchedule,
        job: Callable[[str], None],  # 트리거된 "HH:MM" 전달
        lock_path: Optional[Path] = None,
        on_error_sleep_sec: float = 1.0,
    ):
        self.schedule = schedule
        self.job = job
        self.lock_path = lock_path
        self.on_error_sleep_sec = on_error_sleep_sec

    def run_forever(self) -> None:
        lock = SingleInstanceLock(self.lock_path) if self.lock_path else None

        def _loop() -> None:
            times = self.schedule.times_hhmm
            tz = self.schedule.timezone_name
            print(f"[{_now_str()}] tod-scheduler start | times={times} tz={tz}")

            while True:
                try:
                    nxt_dt = _next_run_dt(times, tz)
                    # nxt_dt는 tz-aware일 수 있음. epoch 변환은 timestamp() 사용.
                    sleep_sec = max(0.5, nxt_dt.timestamp() - time.time())
                    time.sleep(sleep_sec)

                    # “이번에 계산된 nxt_dt” 기준으로 triggered를 결정(오차에 강함)
                    triggered = nxt_dt.strftime("%H:%M")

                    print(f"\n[{_now_str()}] tick@{triggered}")
                    self.job(triggered)

                except KeyboardInterrupt:
                    print(f"\n[{_now_str()}] scheduler stopped by user")
                    break
                except Exception as e:
                    print(f"[{_now_str()}] ERROR in job: {e}")
                    time.sleep(self.on_error_sleep_sec)

        if lock:
            with lock:
                _loop()
        else:
            _loop()
