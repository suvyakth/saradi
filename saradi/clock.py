"""A clock that can run faster than real time and jump forward, for demos and tests."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


class Clock:
    def __init__(self, start: float | None = None, speed: float = 1.0):
        self._lock = threading.Lock()
        self._real_base = time.time()
        self._sim_base = start if start is not None else self._real_base
        self._speed = speed

    def now(self) -> float:
        with self._lock:
            return self._sim_base + (time.time() - self._real_base) * self._speed

    @property
    def speed(self) -> float:
        return self._speed

    def set_speed(self, speed: float) -> None:
        with self._lock:
            current = self._sim_base + (time.time() - self._real_base) * self._speed
            self._real_base, self._sim_base, self._speed = time.time(), current, speed

    def advance(self, minutes: float) -> None:
        with self._lock:
            self._sim_base += minutes * 60


class FixedClock:
    """Test clock: only moves when told to."""

    def __init__(self, start: float):
        self.t = start
        self.speed = 1.0

    def now(self) -> float:
        return self.t

    def advance(self, minutes: float) -> None:
        self.t += minutes * 60

    def set_speed(self, speed: float) -> None:
        self.speed = speed


def hhmm(ts: float | None) -> str:
    if ts is None:
        return "-"
    return datetime.fromtimestamp(ts, IST).strftime("%H:%M")


def weekday(ts: float) -> int:
    return datetime.fromtimestamp(ts, IST).weekday()


def ist(year: int, month: int, day: int, hour: int, minute: int = 0) -> float:
    return datetime(year, month, day, hour, minute, tzinfo=IST).timestamp()
