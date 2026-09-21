"""Executable local LiveKit Agent Server entrypoint."""

import asyncio
import sys
from pathlib import Path
from typing import Final

from livekit.agents import cli

from interview_app.adapters.livekit.agent_server import (
    AgentServerConfiguration,
    build_agent_server,
)
from interview_app.bootstrap import build_interruption_reconciler
from interview_app.entrypoints.environment import load_environment
from interview_app.settings import LaunchSettings, Settings

# Only these modes accept interview jobs; maintenance modes must not touch interview state.
_JOB_ACCEPTING_MODES: Final = frozenset({"dev", "start"})


def main() -> None:
    values = load_environment()
    settings = Settings.from_mapping(values)
    launch = LaunchSettings.from_mapping(values)
    if sys.argv[1:2] and sys.argv[1] in _JOB_ACCEPTING_MODES:
        asyncio.run(_close_interrupted_interviews(launch.sqlite_path))
    server = build_agent_server(
        AgentServerConfiguration(
            settings=settings,
            sqlite_path=launch.sqlite_path,
            agent_name=launch.agent_name,
        )
    )
    cli.run_app(server)


async def _close_interrupted_interviews(sqlite_path: Path) -> None:
    """Close interviews left active by a job process that no longer exists.

    This runs before the server accepts jobs, so no live job of this single local agent server
    can own any interview yet (R03). Without it, one interrupted run blocks every later one.
    """
    database, reconcile = build_interruption_reconciler(sqlite_path)
    await database.migrate()
    result = await reconcile.execute()
    print(
        f"reconciled_interrupted_interviews={len(result.marked_incomplete)} "
        f"resumable={len(result.resumable)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
