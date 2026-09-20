"""Time source contract."""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Provide monotonic elapsed time and timezone-aware UTC timestamps."""

    def monotonic(self) -> float: ...

    def utc_now(self) -> datetime: ...
