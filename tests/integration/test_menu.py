import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from interview_app.adapters.process import ServiceStatus
from interview_app.adapters.sqlite import (
    SqliteDatabase,
    SqliteInterviewStore,
    SqliteRecordingManifestStore,
    SqliteTranscriptStore,
)
from interview_app.adapters.terminal.console import OperatorCancelled
from interview_app.domain.models import (
    DeliveryStatus,
    InterviewId,
    InterviewRecord,
    InterviewState,
    RecordingId,
    RecordingManifest,
    RecordingSegment,
    RecordingSegmentId,
    RecordingStatus,
    Speaker,
    StageId,
    StageKind,
    StageRecord,
    StageState,
    TurnId,
    TurnRecord,
)
from interview_app.entrypoints.menu import InterviewMenu

INJECTION = "\x1b[2JAlex"


class FakeConsole:
    """Answer prompts from a script and record everything the menu printed."""

    def __init__(self, answers: list[str]) -> None:
        self._answers = answers
        self.output: list[str] = []

    def write(self, message: str) -> None:
        self.output.append(message)

    def prompt(self, message: str) -> str:
        self.output.append(message)
        if not self._answers:
            raise OperatorCancelled("No further operator input.")
        return self._answers.pop(0)

    @property
    def printed(self) -> str:
        return "\n".join(self.output)


class FakeSupervisor:
    def __init__(self, *, managed: bool = False, reachable: bool = False) -> None:
        self.managed = managed
        self.reachable = reachable
        self.starts = 0
        self.stops = 0

    @property
    def log_path(self) -> Path:
        return Path("data/logs/menu-services.log")

    def status(self) -> ServiceStatus:
        return ServiceStatus(
            managed_here=self.managed,
            pid=4242 if self.managed else None,
            livekit_reachable=self.reachable,
        )

    def start(self) -> ServiceStatus:
        self.starts += 1
        self.managed = True
        self.reachable = True
        return self.status()

    def stop(self) -> None:
        self.stops += 1
        self.managed = False


async def _seed(database: SqliteDatabase, recordings_root: Path) -> None:
    now = datetime.now(UTC)
    await database.migrate()
    interview_id = InterviewId("menu-interview")
    stage_id = StageId("menu-hr")
    await SqliteInterviewStore(database).create(
        InterviewRecord(
            id=interview_id,
            candidate_name=INJECTION,
            state=InterviewState.INCOMPLETE,
            created_at=now,
        )
    )
    transcripts = SqliteTranscriptStore(database)
    await transcripts.create_stage(
        StageRecord(
            id=stage_id,
            interview_id=interview_id,
            kind=StageKind.HR,
            state=StageState.CLOSED,
            created_at=now,
        )
    )
    await transcripts.append_turn(
        TurnRecord(
            id=TurnId("menu-turn"),
            stage_id=stage_id,
            speaker=Speaker.CANDIDATE,
            text=f"Answer {INJECTION}",
            is_final=True,
            delivery_status=DeliveryStatus.DELIVERED,
            occurred_at=now,
        )
    )
    media = b"RIFF-menu-wave"
    relative_path = "menu-recording/candidate.wav"
    path = recordings_root / relative_path
    path.parent.mkdir(parents=True)
    path.write_bytes(media)
    await SqliteRecordingManifestStore(database).save(
        RecordingManifest(
            id=RecordingId("menu-recording"),
            interview_id=interview_id,
            sample_rate_hz=16_000,
            channels=1,
            sample_width_bytes=2,
            started_at=now,
            completed_at=now,
            status=RecordingStatus.COMPLETE,
            failure=None,
            segments=(
                RecordingSegment(
                    id=RecordingSegmentId("menu-segment"),
                    recording_id=RecordingId("menu-recording"),
                    stage_id=stage_id,
                    speaker=Speaker.CANDIDATE,
                    relative_path=relative_path,
                    offset_seconds=0,
                    duration_seconds=1,
                    checksum_sha256=hashlib.sha256(media).hexdigest(),
                    status=RecordingStatus.COMPLETE,
                    gaps=(),
                ),
            ),
        )
    )


@pytest.fixture
def seeded_menu_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    recordings_root = tmp_path / "recordings"
    asyncio.run(_seed(SqliteDatabase(tmp_path / "menu.sqlite3"), recordings_root))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "menu.sqlite3"))
    monkeypatch.setenv("RECORDINGS_DIR", str(recordings_root))
    return recordings_root


def test_menu_lists_every_function_and_quits_cleanly() -> None:
    console = FakeConsole(["0"])
    supervisor = FakeSupervisor()

    assert InterviewMenu(console=console, supervisor=supervisor).run() == 0
    printed = console.printed

    for label in (
        "Start background services",
        "Start a new interview",
        "Rejoin an existing interview",
        "Show live interview status",
        "List retained interview results",
        "Locate a recording file",
        "List audio devices",
        "Check configuration",
        "Run retention cleanup",
        "Offline dry run",
        "0) Quit",
    ):
        assert label in printed
    assert "services=not started here" in printed
    assert supervisor.stops == 0


def test_quitting_stops_only_services_the_menu_started() -> None:
    supervisor = FakeSupervisor()
    console = FakeConsole(["1", "0"])

    InterviewMenu(console=console, supervisor=supervisor).run()

    assert supervisor.starts == 1
    assert supervisor.stops == 1
    assert "services=running (pid 4242)" in console.printed


def test_closed_input_leaves_the_menu_without_a_traceback() -> None:
    console = FakeConsole([])

    assert InterviewMenu(console=console, supervisor=FakeSupervisor()).run() == 0
    assert "Input closed" in console.printed


def test_unknown_option_is_reported_inertly_and_the_menu_continues() -> None:
    console = FakeConsole(["\x1b[31mnope", "0"])

    InterviewMenu(console=console, supervisor=FakeSupervisor()).run()

    assert "Unknown option: \\x1b[31mnope" in console.printed
    assert "\x1b" not in console.printed


def test_results_are_listed_and_shown_through_the_menu(
    seeded_menu_environment: Path,
) -> None:
    console = FakeConsole(["6", "n", "7", "1", "n", "0"])

    InterviewMenu(console=console, supervisor=FakeSupervisor()).run()
    printed = console.printed

    assert "retained_interviews=1" in printed
    assert "menu-interview" in printed
    assert "HR and technical assessments are independent" in printed
    assert "turn=menu-turn" in printed
    # The injected control sequence is escaped in both the pick list and the report.
    assert "\x1b" not in printed
    assert "\\x1b[2JAlex" in printed


def test_recording_lookup_resolves_the_owned_file_through_the_menu(
    seeded_menu_environment: Path,
) -> None:
    console = FakeConsole(["8", "1", "1", "0"])

    InterviewMenu(console=console, supervisor=FakeSupervisor()).run()

    expected = seeded_menu_environment / "menu-recording" / "candidate.wav"
    assert f"path={expected}" in console.printed


def test_reportable_failures_return_to_the_menu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "empty.sqlite3"))
    monkeypatch.setenv("RECORDINGS_DIR", str(tmp_path / "recordings"))
    console = FakeConsole(["7", "no-such-interview", "0"])

    assert InterviewMenu(console=console, supervisor=FakeSupervisor()).run() == 0
    assert "error=Unknown or expired interview: no-such-interview" in console.printed


def test_starting_an_interview_requires_reachable_livekit(
    seeded_menu_environment: Path,
) -> None:
    console = FakeConsole(["3", "0"])

    InterviewMenu(console=console, supervisor=FakeSupervisor(reachable=False)).run()

    assert "LiveKit is not reachable" in console.printed


def test_a_blocked_interview_explains_how_to_recover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def seed_active() -> None:
        database = SqliteDatabase(tmp_path / "menu.sqlite3")
        await database.migrate()
        await SqliteInterviewStore(database).create(
            InterviewRecord(
                id=InterviewId("still-active"),
                candidate_name="Earlier Candidate",
                state=InterviewState.HR_ACTIVE,
                created_at=datetime.now(UTC),
            )
        )

    asyncio.run(seed_active())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "menu.sqlite3"))
    monkeypatch.setenv("LIVEKIT_API_KEY", "local-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "local-secret")
    console = FakeConsole(["3", "0"])

    InterviewMenu(console=console, supervisor=FakeSupervisor(managed=True, reachable=True)).run()

    printed = console.printed
    assert "error=Active interview already exists: still-active" in printed
    assert "restart the background services" in printed
    assert "choose 2, then 1" in printed
    # Refused before asking anything, so no name or device prompt was shown.
    assert "Candidate name:" not in printed


def test_rejoining_an_incomplete_interview_is_refused_before_any_device_prompt(
    seeded_menu_environment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIVEKIT_API_KEY", "local-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "local-secret")
    console = FakeConsole(["4", "1", "0"])

    InterviewMenu(console=console, supervisor=FakeSupervisor(managed=True, reachable=True)).run()

    printed = console.printed
    assert "menu-interview is incomplete" in printed
    assert "Start a new interview" in printed
    # An empty room would never be answered, so nothing was connected or asked for.
    assert "Input device" not in printed
    assert "Connecting" not in printed
