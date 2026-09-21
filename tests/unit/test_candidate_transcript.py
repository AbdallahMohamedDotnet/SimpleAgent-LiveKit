import asyncio
from types import SimpleNamespace
from typing import Any

from interview_app.adapters.livekit.candidate import (
    CandidateConnection,
    TerminalCandidateClient,
    TranscriptLine,
)
from interview_app.domain.models import Speaker
from interview_app.entrypoints.candidate import print_transcript_line
from interview_app.settings import Secret

CANDIDATE = "candidate-1"


class FakeReader:
    def __init__(self, text: str, *, final: bool | None = None) -> None:
        attributes = {} if final is None else {"lk.transcription_final": str(final).lower()}
        self.info = SimpleNamespace(attributes=attributes)
        self._text = text

    async def read_all(self) -> str:
        return self._text


def _client(lines: list[TranscriptLine], *, fail: bool = False) -> TerminalCandidateClient:
    def record(line: TranscriptLine) -> None:
        if fail:
            raise RuntimeError("display broke")
        lines.append(line)

    return TerminalCandidateClient(
        CandidateConnection(
            url="ws://127.0.0.1:7880",
            api_key=Secret("key"),
            api_secret=Secret("secret"),
            room_name="room",
            identity=CANDIDATE,
        ),
        audio=object(),  # type: ignore[arg-type]
        on_transcript=record,
    )


async def _deliver(client: TerminalCandidateClient, reader: Any, sender: str) -> None:
    client._on_transcription_stream(reader, sender)
    await asyncio.gather(*client._transcript_tasks)


def test_interviewer_and_final_candidate_speech_are_shown_but_interim_is_not() -> None:
    lines: list[TranscriptLine] = []

    async def scenario() -> None:
        client = _client(lines)
        await _deliver(client, FakeReader("Tell me about a project.", final=False), "agent-1")
        await _deliver(client, FakeReader("I led a", final=False), CANDIDATE)
        await _deliver(client, FakeReader("I led a migration.", final=True), CANDIDATE)
        await _deliver(client, FakeReader("   ", final=True), CANDIDATE)

    asyncio.run(scenario())

    assert lines == [
        TranscriptLine(Speaker.INTERVIEWER, "Tell me about a project."),
        TranscriptLine(Speaker.CANDIDATE, "I led a migration."),
    ]


def test_a_failing_display_does_not_raise_into_the_interview() -> None:
    async def scenario() -> None:
        await _deliver(_client([], fail=True), FakeReader("Hello", final=True), "agent-1")

    asyncio.run(scenario())


def test_printed_transcript_neutralizes_terminal_escapes(
    capsys: Any,
) -> None:
    print_transcript_line(TranscriptLine(Speaker.INTERVIEWER, "\x1b[2Jhello\nworld"))

    printed = capsys.readouterr().out
    assert printed == "[Interviewer] \\x1b[2Jhello world\n"
