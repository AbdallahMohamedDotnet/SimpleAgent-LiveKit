import asyncio
from datetime import UTC, datetime
from pathlib import Path

from interview_app.adapters.fakes import FakeClock
from interview_app.adapters.livekit.agent_server import _record_early_job_exit
from interview_app.adapters.sqlite import SqliteDatabase, SqliteInterviewStore, SqliteRecoveryStore
from interview_app.application.launch import StartInterview
from interview_app.application.ports.interview_launch import (
    LaunchBinding,
    LaunchRequest,
    LaunchStatus,
)
from interview_app.bootstrap import build_interruption_reconciler
from interview_app.domain.models import InterviewId, InterviewRecord, InterviewState


class RecordingGateway:
    def __init__(self) -> None:
        self.requests: list[LaunchRequest] = []

    async def launch(self, request: LaunchRequest) -> LaunchBinding:
        self.requests.append(request)
        return LaunchBinding(room_sid="RM_next", dispatch_id="dispatch-next")

    async def get_status(self, *, room_name: str, candidate_identity: str) -> LaunchStatus:
        return LaunchStatus(True, True, False, False)

    async def cancel(self, room_name: str) -> None:
        return None


async def _orphan(database: SqliteDatabase, state: InterviewState) -> InterviewRecord:
    await database.migrate()
    record = InterviewRecord(
        id=InterviewId("orphaned-interview"),
        candidate_name="Earlier Candidate",
        state=state,
        created_at=datetime.now(UTC),
        room_name="interview-orphaned",
        room_sid="RM_orphaned",
        candidate_identity="candidate-orphaned",
    )
    await SqliteInterviewStore(database).create(record)
    return record


def test_startup_reconciliation_unblocks_the_next_interview(tmp_path: Path) -> None:
    async def exercise() -> None:
        path = tmp_path / "interviews.sqlite3"
        interviews = SqliteInterviewStore(SqliteDatabase(path))
        await _orphan(SqliteDatabase(path), InterviewState.HR_ACTIVE)
        gateway = RecordingGateway()
        start = StartInterview(clock=FakeClock(), interviews=interviews, gateway=gateway)

        # Before reconciliation the stale record blocks a new interview without dispatching.
        try:
            await start.execute("Next Candidate")
        except RuntimeError as error:
            assert "orphaned-interview" in str(error)
        else:
            raise AssertionError("The stale active interview should block a new one.")
        assert gateway.requests == []

        database, reconcile = build_interruption_reconciler(path)
        await database.migrate()
        result = await reconcile.execute()

        assert result.marked_incomplete == (InterviewId("orphaned-interview"),)
        assert (await interviews.get(InterviewId("orphaned-interview"))).state is (
            InterviewState.INCOMPLETE
        )
        assert await interviews.find_active() is None
        started = await start.execute("Next Candidate")
        assert (await interviews.find_active()) == started.interview
        assert len(gateway.requests) == 1

    asyncio.run(exercise())


def test_a_job_that_ends_early_closes_its_interview_honestly(tmp_path: Path) -> None:
    async def exercise() -> None:
        database = SqliteDatabase(tmp_path / "interviews.sqlite3")
        record = await _orphan(database, InterviewState.HR_ACTIVE)
        store = SqliteRecoveryStore(database)

        await _record_early_job_exit(store, record)
        # A second call, as after a retry or cancellation, must not raise and hide the cause.
        await _record_early_job_exit(store, record)

        interview = await SqliteInterviewStore(database).get(record.id)
        assert interview.state is InterviewState.INCOMPLETE

    asyncio.run(exercise())


def test_a_finished_interview_is_never_rewritten_as_incomplete(tmp_path: Path) -> None:
    async def exercise() -> None:
        database = SqliteDatabase(tmp_path / "interviews.sqlite3")
        record = await _orphan(database, InterviewState.INTERVIEW_FINISHED)

        await _record_early_job_exit(SqliteRecoveryStore(database), record)

        interview = await SqliteInterviewStore(database).get(record.id)
        assert interview.state is InterviewState.INTERVIEW_FINISHED

    asyncio.run(exercise())
