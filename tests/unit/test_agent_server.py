import asyncio
from pathlib import Path

import pytest

from interview_app.adapters.fakes import FakeClock, InMemoryInterviewStore
from interview_app.adapters.livekit.agent_server import (
    AgentServerConfiguration,
    InterviewJobMetadata,
    InvalidJobMetadataError,
    _wait_for_dispatched_interview,
    build_agent_server,
)
from interview_app.domain.models import InterviewId, InterviewRecord, InterviewState
from interview_app.settings import Settings


def _settings() -> Settings:
    return Settings.from_mapping(
        {
            "LIVEKIT_API_KEY": "devkey",
            "LIVEKIT_API_SECRET": "secret",
            "OPENROUTER_API_KEY": "offline-test",
            "ELEVEN_API_KEY": "offline-test",
            "HR_VOICE_ID": "hr-voice",
            "TECH_VOICE_ID": "technical-voice",
        }
    )


def test_dispatch_metadata_is_narrowly_validated() -> None:
    parsed = InterviewJobMetadata.parse(
        '{"interview_id":"interview-1","candidate_identity":"candidate-1"}'
    )
    assert parsed.interview_id == InterviewId("interview-1")
    assert parsed.candidate_identity == "candidate-1"

    for raw in ("", "[]", "{}", '{"interview_id":"x"}'):
        with pytest.raises(InvalidJobMetadataError):
            InterviewJobMetadata.parse(raw)


def test_agent_server_registers_the_fixed_dispatch_name_without_network() -> None:
    server = build_agent_server(
        AgentServerConfiguration(
            settings=_settings(),
            sqlite_path=Path("unused.sqlite3"),
            agent_name="interview-agent",
        )
    )
    assert server is not None


def test_agent_job_waits_for_the_launch_record_commit() -> None:
    async def exercise() -> None:
        store = InMemoryInterviewStore()
        identifier = InterviewId("interview-race")

        async def commit() -> None:
            await asyncio.sleep(0)
            await store.create(
                InterviewRecord(
                    id=identifier,
                    candidate_name="Candidate",
                    state=InterviewState.CREATED,
                    created_at=FakeClock().utc_now(),
                )
            )

        commit_task = asyncio.create_task(commit())
        record = await _wait_for_dispatched_interview(
            store,
            identifier,
            attempts=3,
            delay_seconds=0,
        )
        await commit_task
        assert record.id == identifier

    asyncio.run(exercise())
