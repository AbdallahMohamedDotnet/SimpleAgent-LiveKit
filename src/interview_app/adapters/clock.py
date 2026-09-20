"""Production clock backed by the operating system."""

import time
from datetime import UTC, datetime


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def utc_now(self) -> datetime:
        return datetime.now(UTC)
