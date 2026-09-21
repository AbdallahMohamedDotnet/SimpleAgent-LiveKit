"""Create or join an interview as the terminal audio participant."""

from __future__ import annotations

from interview_app.adapters.clock import SystemClock
from interview_app.adapters.livekit.candidate import (
    CandidateConnection,
    SoundDeviceBackend,
    TerminalCandidateClient,
)
from interview_app.adapters.livekit.launcher import LiveKitInterviewLaunchGateway
from interview_app.adapters.sqlite import SqliteDatabase, SqliteInterviewStore
from interview_app.application.launch import StartInterview
from interview_app.domain.models import InterviewId, InterviewRecord
from interview_app.settings import ControlSettings


async def start_and_join(
    settings: ControlSettings,
    *,
    candidate_name: str,
    input_device: str | None,
    output_device: str | None,
) -> InterviewRecord:
    audio = SoundDeviceBackend()
    database = SqliteDatabase(settings.sqlite_path)
    await database.migrate()
    interviews = SqliteInterviewStore(database)
    gateway = LiveKitInterviewLaunchGateway(
        url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
        agent_name=settings.agent_name,
    )
    started = await StartInterview(
        clock=SystemClock(),
        interviews=interviews,
        gateway=gateway,
    ).execute(candidate_name)
    await _join(
        settings,
        started.interview,
        input_device=input_device,
        output_device=output_device,
        audio=audio,
    )
    return started.interview


async def join_existing(
    settings: ControlSettings,
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
    settings: ControlSettings,
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
