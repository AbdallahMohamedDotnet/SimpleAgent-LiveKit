"""Executable local LiveKit Agent Server entrypoint."""

from livekit.agents import cli

from interview_app.adapters.livekit.agent_server import (
    AgentServerConfiguration,
    build_agent_server,
)
from interview_app.entrypoints.environment import load_environment
from interview_app.settings import LaunchSettings, Settings


def main() -> None:
    values = load_environment()
    settings = Settings.from_mapping(values)
    launch = LaunchSettings.from_mapping(values)
    server = build_agent_server(
        AgentServerConfiguration(
            settings=settings,
            sqlite_path=launch.sqlite_path,
            agent_name=launch.agent_name,
        )
    )
    cli.run_app(server)


if __name__ == "__main__":
    main()
