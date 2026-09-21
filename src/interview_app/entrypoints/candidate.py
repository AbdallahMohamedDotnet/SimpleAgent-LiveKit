"""Create or join an interview as the terminal audio participant."""

from __future__ import annotations

from interview_app.adapters.livekit.candidate import (
    CandidateConnection,
    SoundDeviceBackend,
    TerminalCandidateClient,
)
from interview_app.adapters.sqlite import SqliteDatabase, SqliteInterviewStore
from interview_app.application.ports.interview_store import (
    ActiveInterviewExistsError,
)
from interview_app.bootstrap import build_start_interview
from interview_app.domain.models import InterviewId, InterviewRecord
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
    audio = SoundDeviceBackend()
    database = SqliteDatabase(settings.sqlite_path)
    await database.migrate()
    interview = await SqliteInterviewStore(database).get(interview_id)
    await _join(
        settings,
        interview,
        input_device=input_device,
        output_device=output_device,
        audio=audio,
    )
    return interview


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
    )
    print(f"interview_id={interview.id}")
    print(f"room={interview.room_name}")
    print("candidate_audio=connecting")
    await client.run()
