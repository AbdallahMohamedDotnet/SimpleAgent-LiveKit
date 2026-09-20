"""Pure timing policies for active stage deadlines and genuine idle."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True, slots=True)
class StageTiming:
    elapsed_seconds: float
    remaining_seconds: float
    deadline_reached: bool
    answer_may_finish: bool
    overrun_seconds: float


class ActiveStageTimer:
    """Count substantive conversation and ordinary thinking using monotonic time."""

    def __init__(self, *, target_seconds: float = 300.0) -> None:
        if target_seconds <= 0:
            raise ValueError("target_seconds must be positive.")
        self._target = target_seconds
        self._started_at: float | None = None
        self._paused_at: float | None = None
        self._excluded_seconds = 0.0

    def start(self, now: float) -> None:
        if self._started_at is not None:
            raise RuntimeError("Stage timer is already started.")
        self._started_at = now

    def pause_for_recovery(self, now: float) -> None:
        self._require_started()
        if self._paused_at is not None:
            raise RuntimeError("Stage timer is already paused.")
        self._paused_at = now

    def resume_after_recovery(self, now: float) -> None:
        if self._paused_at is None:
            raise RuntimeError("Stage timer is not paused.")
        if now < self._paused_at:
            raise ValueError("Monotonic time cannot move backwards.")
        self._excluded_seconds += now - self._paused_at
        self._paused_at = None

    def status(self, now: float, *, answer_in_progress: bool) -> StageTiming:
        started_at = self._require_started()
        effective_now = self._paused_at if self._paused_at is not None else now
        elapsed = effective_now - started_at - self._excluded_seconds
        if elapsed < 0:
            raise ValueError("Monotonic time cannot precede stage start.")
        deadline = elapsed >= self._target
        return StageTiming(
            elapsed_seconds=elapsed,
            remaining_seconds=max(0.0, self._target - elapsed),
            deadline_reached=deadline,
            answer_may_finish=deadline and answer_in_progress,
            overrun_seconds=max(0.0, elapsed - self._target),
        )

    def can_start_question(self, now: float) -> bool:
        return not self.status(now, answer_in_progress=False).deadline_reached

    def _require_started(self) -> float:
        if self._started_at is None:
            raise RuntimeError("Stage timer starts with the first substantive question.")
        return self._started_at


class IdleCheckInPolicy:
    """Debounce one reminder after genuine idle, independent of endpointing."""

    def __init__(self, *, threshold_seconds: float = 5.0) -> None:
        if threshold_seconds <= 0:
            raise ValueError("threshold_seconds must be positive.")
        self._threshold = threshold_seconds
        self._last_activity: float | None = None
        self._thinking_until: float | None = None
        self._reminded = False

    def observe_activity(self, now: float) -> None:
        self._last_activity = now
        self._thinking_until = None
        self._reminded = False

    def hold_for_thinking(self, now: float, *, duration_seconds: float) -> None:
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive.")
        self._thinking_until = now + duration_seconds

    def should_check_in(
        self,
        now: float,
        *,
        candidate_speaking: bool,
        agent_speaking: bool,
        agent_generating: bool,
    ) -> bool:
        if self._last_activity is None or self._reminded:
            return False
        if candidate_speaking or agent_speaking or agent_generating:
            return False
        if self._thinking_until is not None and now < self._thinking_until:
            return False
        if now - self._last_activity < self._threshold:
            return False
        self._reminded = True
        return True


@dataclass(frozen=True, slots=True)
class RecoveryStatus:
    remaining_seconds: float
    exhausted: bool


class RecoveryBudget:
    """One wall-clock deadline shared by all retries in a recovery incident."""

    def __init__(self, *, started_at: float, budget_seconds: float = 120.0) -> None:
        if budget_seconds <= 0:
            raise ValueError("budget_seconds must be positive.")
        self._started_at = started_at
        self._deadline = started_at + budget_seconds

    def status(self, now: float) -> RecoveryStatus:
        if now < self._started_at:
            raise ValueError("Monotonic time cannot precede recovery start.")
        remaining = max(0.0, self._deadline - now)
        return RecoveryStatus(remaining_seconds=remaining, exhausted=remaining == 0.0)

    def bounded_delay(self, *, now: float, attempt: int) -> float:
        if attempt < 1:
            raise ValueError("attempt must be at least 1.")
        remaining = self.status(now).remaining_seconds
        exponential = min(10.0, float(2 ** (attempt - 1)))
        return min(remaining, exponential)


class RetentionPolicy:
    """Expire interview data exactly 30 UTC days after interview start."""

    def __init__(self, *, retention_days: int = 30) -> None:
        if retention_days != 30:
            raise ValueError("Interview retention is fixed at 30 days.")
        self._duration = timedelta(days=retention_days)

    def expires_at(self, interview_started_at: datetime) -> datetime:
        if interview_started_at.tzinfo is None:
            raise ValueError("Interview start must be timezone-aware.")
        return interview_started_at.astimezone(UTC) + self._duration

    def is_expired(self, interview_started_at: datetime, *, now: datetime) -> bool:
        if now.tzinfo is None:
            raise ValueError("Current time must be timezone-aware.")
        return now.astimezone(UTC) >= self.expires_at(interview_started_at)

    def expired_start_cutoff(self, *, now: datetime) -> datetime:
        """Return the newest interview start that is already expired."""
        if now.tzinfo is None:
            raise ValueError("Current time must be timezone-aware.")
        return now.astimezone(UTC) - self._duration
