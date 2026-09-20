"""Operator command-line interface."""

import argparse
import asyncio
import os
from collections.abc import Sequence

from interview_app.application.interview import InvalidCandidateNameError
from interview_app.bootstrap import build_dry_run_interview
from interview_app.entrypoints.worker import run_worker
from interview_app.settings import ConfigurationError, ScoringSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="interview",
        description="Local voice interview operator commands.",
        epilog=(
            "Planned, not available yet: run, results, cleanup, status. "
            "The dry-run command is offline and never contacts a provider."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    dry_run = commands.add_parser(
        "dry-run", help="Exercise the typed two-stage lifecycle without network access."
    )
    dry_run.add_argument("--name", required=True, help="Candidate display name.")
    worker = commands.add_parser(
        "worker", help="Process durable transcript assessment tasks through OpenRouter."
    )
    worker.add_argument(
        "--once",
        action="store_true",
        help="Check for one task and exit instead of polling continuously.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "dry-run":
        try:
            result = asyncio.run(build_dry_run_interview().execute(arguments.name))
        except InvalidCandidateNameError as error:
            parser.error(str(error))
        print(f"interview_id={result.interview.id}")
        print(f"state={result.interview.state.value}")
        for event in result.events:
            print(f"event={event.stage_kind.value}:{event.type.value}")
        return 0
    if arguments.command == "worker":
        try:
            settings = ScoringSettings.from_mapping(os.environ)
            outcome = asyncio.run(run_worker(settings, once=bool(arguments.once)))
        except ConfigurationError as error:
            parser.error(str(error))
        if outcome is None:
            print("score_task=none")
        else:
            print(f"score_task_state={outcome.task_state.value}")
            if outcome.result is not None:
                print(f"score_task_id={outcome.result.task_id}")
        return 0
    parser.error(f"Unsupported command: {arguments.command}")


if __name__ == "__main__":
    raise SystemExit(main())
