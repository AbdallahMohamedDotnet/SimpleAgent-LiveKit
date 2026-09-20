"""Verify sequential production stage adapters against one local LiveKit room.

This probe uses real RTC connections and AgentSession lifecycles with model activity
disabled. It verifies room/session ownership, not microphone or provider behavior.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime

from livekit import api, rtc
from livekit.agents import Agent, AgentSession

from interview_app.adapters.livekit import LiveKitStageRuntime
from interview_app.domain.models import (
    InterviewId,
    StageId,
    StageKind,
    StageRecord,
    StageStartContext,
    StageState,
)


class ProbeClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def utc_now(self) -> datetime:
        return datetime.now(UTC)


def _token(*, api_key: str, api_secret: str, room: str, identity: str) -> str:
    return (
        api.AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_grants(api.VideoGrants(room_join=True, room=room))
        .to_jwt()
    )


async def _connect(
    *,
    url: str,
    api_key: str,
    api_secret: str,
    room_name: str,
    identity: str,
) -> rtc.Room:
    room = rtc.Room()
    await room.connect(
        url,
        _token(
            api_key=api_key,
            api_secret=api_secret,
            room=room_name,
            identity=identity,
        ),
    )
    return room


async def _run(args: argparse.Namespace) -> None:
    candidate_identity = "p03-candidate"
    candidate_room = await _connect(
        url=args.url,
        api_key=args.api_key,
        api_secret=args.api_secret,
        room_name=args.room,
        identity=candidate_identity,
    )
    agent_room = await _connect(
        url=args.url,
        api_key=args.api_key,
        api_secret=args.api_secret,
        room_name=args.room,
        identity="p03-agent-job",
    )
    room_sid = await agent_room.sid
    clock = ProbeClock()
    interview_id = InterviewId("p03-live-probe")
    results: list[dict[str, object]] = []

    try:
        for kind in (StageKind.HR, StageKind.TECHNICAL):
            session: AgentSession[object] = AgentSession()
            runtime = LiveKitStageRuntime(
                clock=clock,
                room=agent_room,
                session=session,
                agent=Agent(instructions=f"P03 {kind.value} lifecycle probe."),
            )
            context = StageStartContext(
                stage=StageRecord(
                    id=StageId(f"p03-{kind.value}"),
                    interview_id=interview_id,
                    kind=kind,
                    state=StageState.ACTIVE,
                    created_at=clock.utc_now(),
                    session_reference=f"p03-session-{kind.value}",
                ),
                room_sid=room_sid,
                candidate_identity=candidate_identity,
            )
            started = await runtime.start(context)
            # AgentSession.start returns while RTC publication callbacks may still
            # be settling. A real stage remains active for minutes; the probe gives
            # that asynchronous startup a brief opportunity to reach steady state.
            await asyncio.sleep(0.25)
            draining = await runtime.drain()
            closed = await runtime.close()
            results.append(
                {
                    "stage": kind.value,
                    "session_reference": context.stage.session_reference,
                    "events": [started.type.value, draining.type.value, closed.type.value],
                    "room_connected_after_close": agent_room.isconnected(),
                    "room_sid_unchanged": await agent_room.sid == room_sid,
                    "candidate_still_connected": candidate_room.isconnected(),
                }
            )
    finally:
        await agent_room.disconnect()
        await candidate_room.disconnect()

    print(
        json.dumps(
            {
                "room": args.room,
                "room_sid": room_sid,
                "candidate_identity": candidate_identity,
                "stages": results,
                "distinct_session_references": (
                    results[0]["session_reference"] != results[1]["session_reference"]
                ),
            },
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://127.0.0.1:7880")
    parser.add_argument("--api-key", default="devkey")
    parser.add_argument("--api-secret", default="secret")
    parser.add_argument("--room", default="p03-handoff-probe")
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
