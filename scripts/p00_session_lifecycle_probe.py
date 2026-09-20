"""Probe sequential AgentSession cleanup against one connected local room.

This is compatibility evidence, not production application wiring. It deliberately
disables media and model activity so it can isolate ownership of the RTC room from
ownership of each AgentSession.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from livekit import api, rtc
from livekit.agents import Agent, AgentSession, room_io


def _token(*, api_key: str, api_secret: str, room: str, identity: str) -> str:
    return (
        api.AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_grants(api.VideoGrants(room_join=True, room=room))
        .to_jwt()
    )


async def _run(args: argparse.Namespace) -> None:
    room = rtc.Room()
    await room.connect(
        args.url,
        _token(
            api_key=args.api_key,
            api_secret=args.api_secret,
            room=args.room,
            identity=args.identity,
        ),
    )
    room_sid = await room.sid
    local_sid = room.local_participant.sid
    results: list[dict[str, object]] = []

    try:
        options = room_io.RoomOptions(
            text_input=False,
            audio_input=False,
            video_input=False,
            audio_output=False,
            text_output=False,
            participant_identity="p00-terminal",
            close_on_disconnect=False,
            delete_room_on_close=False,
        )

        for stage in ("hr", "technical"):
            session = AgentSession()
            await session.start(
                agent=Agent(instructions=f"P00 lifecycle probe for {stage}."),
                room=room,
                room_options=options,
            )
            await session.aclose()
            results.append(
                {
                    "stage": stage,
                    "session_closed": True,
                    "room_connected_after_close": room.isconnected(),
                    "room_sid_unchanged": await room.sid == room_sid,
                    "local_participant_sid_unchanged": room.local_participant.sid == local_sid,
                }
            )
    finally:
        await room.disconnect()

    print(
        json.dumps(
            {
                "room": args.room,
                "room_sid": room_sid,
                "local_participant_sid": local_sid,
                "stages": results,
                "room_disconnected_by_probe": not room.isconnected(),
            },
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://127.0.0.1:7880")
    parser.add_argument("--api-key", default="devkey")
    parser.add_argument("--api-secret", default="secret")
    parser.add_argument("--room", default="p00-compatibility")
    parser.add_argument("--identity", default="p00-session-probe")
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
