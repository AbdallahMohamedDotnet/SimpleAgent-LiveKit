from datetime import UTC, datetime, timedelta

from interview_app.domain.policies import (
    ActiveStageTimer,
    IdleCheckInPolicy,
    RecoveryBudget,
    RetentionPolicy,
)


def test_stage_deadline_finishes_current_answer_and_excludes_recovery() -> None:
    timer = ActiveStageTimer(target_seconds=300)
    timer.start(10)
    assert timer.can_start_question(309.9)
    timer.pause_for_recovery(310)
    assert timer.status(400, answer_in_progress=True).elapsed_seconds == 300
    timer.resume_after_recovery(430)
    assert not timer.can_start_question(430)

    at_deadline = timer.status(430, answer_in_progress=True)
    assert at_deadline.deadline_reached
    assert at_deadline.answer_may_finish
    completed = timer.status(437.5, answer_in_progress=False)
    assert completed.overrun_seconds == 7.5
    assert not completed.answer_may_finish


def test_idle_checkin_is_suppressed_and_debounced() -> None:
    idle = IdleCheckInPolicy(threshold_seconds=5)
    idle.observe_activity(100)
    assert not idle.should_check_in(
        105, candidate_speaking=True, agent_speaking=False, agent_generating=False
    )
    assert not idle.should_check_in(
        105, candidate_speaking=False, agent_speaking=False, agent_generating=True
    )
    idle.hold_for_thinking(105, duration_seconds=20)
    assert not idle.should_check_in(
        124.9, candidate_speaking=False, agent_speaking=False, agent_generating=False
    )
    assert idle.should_check_in(
        125, candidate_speaking=False, agent_speaking=False, agent_generating=False
    )
    assert not idle.should_check_in(
        130, candidate_speaking=False, agent_speaking=False, agent_generating=False
    )
    idle.observe_activity(131)
    assert idle.should_check_in(
        136, candidate_speaking=False, agent_speaking=False, agent_generating=False
    )


def test_recovery_retries_share_one_two_minute_deadline() -> None:
    budget = RecoveryBudget(started_at=100.0)
    assert budget.bounded_delay(now=100.0, attempt=1) == 1.0
    assert budget.bounded_delay(now=105.0, attempt=4) == 8.0
    assert budget.bounded_delay(now=219.5, attempt=9) == 0.5
    assert budget.status(220.0).exhausted
    assert budget.bounded_delay(now=240.0, attempt=10) == 0.0


def test_retention_expires_exactly_thirty_utc_days_after_start() -> None:
    policy = RetentionPolicy()
    started = datetime(2026, 9, 20, 18, 0, tzinfo=UTC)
    assert policy.expires_at(started) == started + timedelta(days=30)
    assert not policy.is_expired(
        started,
        now=started + timedelta(days=30) - timedelta(microseconds=1),
    )
    assert policy.is_expired(started, now=started + timedelta(days=30))
