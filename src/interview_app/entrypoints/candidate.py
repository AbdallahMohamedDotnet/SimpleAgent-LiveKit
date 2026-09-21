"""Create or join an interview as the terminal audio participant."""

from __future__ import annotations

from datetime import UTC, datetime

from interview_app.adapters.livekit.candidate import (
    CandidateConnection,
    SoundDeviceBackend,
    TerminalCandidateClient,
    TranscriptLine,
)
from interview_app.adapters.sqlite import (
    SqliteDatabase,
    SqliteInterviewStore,
    SqliteResultsReader,
)
from interview_app.adapters.terminal.sanitize import sanitize_line
from interview_app.application.ports.interview_launch import InterviewLaunchError
from interview_app.application.ports.interview_store import (
    ActiveInterviewExistsError,
    InterviewStateConflictError,
)
from interview_app.bootstrap import build_start_interview, launch_gateway
from interview_app.domain.models import InterviewId, InterviewRecord, InterviewState, Speaker
from interview_app.settings import LaunchSettings

ACTIVE_INTERVIEW_HINT = (
    "Only one interview can be active at a time. If that interview is still running, finish it "
    "first. If it was interrupted, restart the background services: the agent server closes "
    "interrupted interviews as incomplete when it starts."
)


async def ensure_no_active_interview(settings: LaunchSettings) -> None:
    """Fail before any prompt, device or room work when R03 would reject a new interview."""
    database = SqliteDatabase(settings.sqlite_path)
    await database.migrate()
    active = await SqliteInterviewStore(database).find_active()
    if active is not None:
        raise ActiveInterviewExistsError(active.id)


_NOT_REJOINABLE_STATES = frozenset({InterviewState.INCOMPLETE, InterviewState.INTERVIEW_FINISHED})
_START_NEW_HINT = "Choose 'Start a new interview' instead."


async def ensure_rejoinable(settings: LaunchSettings, interview_id: InterviewId) -> InterviewRecord:
    """Refuse a rejoin that nobody would answer.

    Joining a room whose interview job has ended, or whose room no longer exists (a restarted
    ``livekit-server --dev`` forgets every room), silently creates an empty room: no agent is
    dispatched, so the candidate hears nothing. Fail loudly before any device is opened.
    """
    database = SqliteDatabase(settings.sqlite_path)
    await database.migrate()
    interview = await SqliteInterviewStore(database).get(interview_id)
    if interview.state in _NOT_REJOINABLE_STATES:
        raise InterviewStateConflictError(
            f"Interview {interview.id} is {interview.state.value}; its interviewer is no longer "
            f"running, so rejoining would connect to an empty room. {_START_NEW_HINT}"
        )
    if interview.room_name is None or interview.candidate_identity is None:
        raise InterviewStateConflictError(
            f"Interview {interview.id} has no LiveKit room binding. {_START_NEW_HINT}"
        )
    live = await launch_gateway(settings).get_status(
        room_name=interview.room_name,
        candidate_identity=interview.candidate_identity,
    )
    if not live.room_available or not live.agent_joined:
        raise InterviewLaunchError(
            f"Interview {interview.id} has no running interviewer in its LiveKit room "
            f"(room_available={live.room_available}, agent_joined={live.agent_joined}). Make "
            f"sure the background services are running. {_START_NEW_HINT}"
        )
    return interview


async def start_and_join(
    settings: LaunchSettings,
    *,
    candidate_name: str,
    input_device: str | None,
    output_device: str | None,
) -> InterviewRecord:
    audio = SoundDeviceBackend()
    database, start_interview = build_start_interview(settings)
    await database.migrate()
    started = await start_interview.execute(candidate_name)
    await _join(
        settings,
        started.interview,
        input_device=input_device,
        output_device=output_device,
        audio=audio,
    )
    return started.interview


async def join_existing(
    settings: LaunchSettings,
    *,
    interview_id: InterviewId,
    input_device: str | None,
    output_device: str | None,
) -> InterviewRecord:
    interview = await ensure_rejoinable(settings, interview_id)
    audio = SoundDeviceBackend()
    await print_transcript_so_far(settings, interview_id)
    await _join(
        settings,
        interview,
        input_device=input_device,
        output_device=output_device,
        audio=audio,
    )
    return interview


_SPEAKER_LABELS = {Speaker.INTERVIEWER: "Interviewer", Speaker.CANDIDATE: "You"}


def print_transcript_line(line: TranscriptLine) -> None:
    """Show one spoken turn; recognised speech and model text are untrusted, so it is escaped."""
    text = sanitize_line(" ".join(line.text.split()))
    print(f"[{_SPEAKER_LABELS[line.speaker]}] {text}", flush=True)


async def print_transcript_so_far(settings: LaunchSettings, interview_id: InterviewId) -> None:
    """Replay what was already said, so a rejoining candidate sees the conversation so far."""
    database = SqliteDatabase(settings.sqlite_path)
    await database.migrate()
    result = await SqliteResultsReader(database).get_interview(interview_id, now=datetime.now(UTC))
    turns = [turn for stage in result.stages for turn in stage.turns]
    if not turns:
        return
    print("--- transcript so far ---")
    for turn in turns:
        print_transcript_line(TranscriptLine(speaker=turn.speaker, text=turn.text))


async def _join(
    settings: LaunchSettings,
    interview: InterviewRecord,
    *,
    input_device: str | None,
    output_device: str | None,
    audio: SoundDeviceBackend,
) -> None:
    if interview.room_name is None or interview.candidate_identity is None:
        raise RuntimeError("Interview has no durable LiveKit room binding.")
    client = TerminalCandidateClient(
        CandidateConnection(
            url=settings.livekit_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
            room_name=interview.room_name,
            identity=interview.candidate_identity,
            input_device=input_device,
            output_device=output_device,
        ),
        audio=audio,
        on_transcript=print_transcript_line,
    )
    print(f"interview_id={interview.id}")
    print(f"room={interview.room_name}")
    print("candidate_audio=connecting")
    print("--- live transcript ---", flush=True)
    await client.run()
