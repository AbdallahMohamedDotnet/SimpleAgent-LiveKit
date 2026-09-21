"""Operator command-line interface."""

import argparse
import asyncio
from collections.abc import Sequence

from interview_app.adapters.livekit.candidate import (
    CandidateAudioUnavailableError,
    SoundDeviceBackend,
)
from interview_app.application.interview import InvalidCandidateNameError
from interview_app.bootstrap import build_dry_run_interview
from interview_app.domain.models import InterviewId
from interview_app.entrypoints.candidate import join_existing, start_and_join
from interview_app.entrypoints.cleanup import run_cleanup
from interview_app.entrypoints.control import run_control
from interview_app.entrypoints.environment import load_environment
from interview_app.entrypoints.results import run_results
from interview_app.entrypoints.worker import run_worker
from interview_app.settings import (
    CleanupSettings,
    ConfigurationError,
    ControlSettings,
    ResultsSettings,
    ScoringSettings,
    Settings,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="interview",
        description="Local voice interview operator commands.",
        epilog=(
            "Start the ROOM Agent Server with 'interview-agent dev' before using run/join. "
            "The dry-run command remains offline and never contacts a provider."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    dry_run = commands.add_parser(
        "dry-run", help="Exercise the typed two-stage lifecycle without network access."
    )
    dry_run.add_argument("--name", required=True, help="Candidate display name.")
    run = commands.add_parser(
        "run", help="Create an interview and join its room with terminal microphone audio."
    )
    run.add_argument("--name", required=True, help="Candidate display name.")
    _add_audio_device_arguments(run)
    join = commands.add_parser(
        "join", help="Join an already-created interview with terminal microphone audio."
    )
    join.add_argument("--interview-id", required=True, help="Generated interview ID.")
    _add_audio_device_arguments(join)
    commands.add_parser("devices", help="List available terminal microphone and speaker devices.")
    worker = commands.add_parser(
        "worker", help="Process durable transcript assessment tasks through OpenRouter."
    )
    worker.add_argument(
        "--once",
        action="store_true",
        help="Check for one task and exit instead of polling continuously.",
    )
    commands.add_parser(
        "control",
        help="Serve the localhost operator console for room creation and agent dispatch.",
    )
    commands.add_parser(
        "cleanup",
        help="Delete interviews and owned artifacts whose 30-day retention has expired.",
    )
    commands.add_parser(
        "results",
        help="Serve the read-only interview results viewer on 127.0.0.1.",
    )
    commands.add_parser(
        "config-check",
        help="Validate every .env setting without printing secret values.",
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
            scoring_settings = ScoringSettings.from_mapping(load_environment())
            outcome = asyncio.run(run_worker(scoring_settings, once=bool(arguments.once)))
        except ConfigurationError as error:
            parser.error(str(error))
        if outcome is None:
            print("score_task=none")
        else:
            print(f"score_task_state={outcome.task_state.value}")
            if outcome.result is not None:
                print(f"score_task_id={outcome.result.task_id}")
        return 0
    if arguments.command in {"run", "join"}:
        try:
            control_settings = ControlSettings.from_mapping(load_environment())
            if arguments.command == "run":
                asyncio.run(
                    start_and_join(
                        control_settings,
                        candidate_name=arguments.name,
                        input_device=arguments.input_device,
                        output_device=arguments.output_device,
                    )
                )
            else:
                asyncio.run(
                    join_existing(
                        control_settings,
                        interview_id=InterviewId(arguments.interview_id),
                        input_device=arguments.input_device,
                        output_device=arguments.output_device,
                    )
                )
        except (CandidateAudioUnavailableError, ConfigurationError) as error:
            parser.error(str(error))
        except KeyboardInterrupt:
            print("candidate_audio=disconnected")
        return 0
    if arguments.command == "devices":
        try:
            print(SoundDeviceBackend().devices())
        except CandidateAudioUnavailableError as error:
            parser.error(str(error))
        return 0
    if arguments.command == "cleanup":
        try:
            cleanup_settings = CleanupSettings.from_mapping(load_environment())
            report = asyncio.run(run_cleanup(cleanup_settings))
        except ConfigurationError as error:
            parser.error(str(error))
        print(f"cleanup_prepared={report.prepared}")
        print(f"cleanup_deleted={len(report.deleted)}")
        print(f"cleanup_failed={len(report.failed)}")
        return 1 if report.failed else 0
    if arguments.command == "results":
        try:
            results_settings = ResultsSettings.from_mapping(load_environment())
            run_results(results_settings)
        except ConfigurationError as error:
            parser.error(str(error))
        return 0
    if arguments.command == "control":
        try:
            control_settings = ControlSettings.from_mapping(load_environment())
            run_control(control_settings)
        except ConfigurationError as error:
            parser.error(str(error))
        return 0
    if arguments.command == "config-check":
        try:
            values = load_environment()
            Settings.from_mapping(values)
            ScoringSettings.from_mapping(values)
            CleanupSettings.from_mapping(values)
            ResultsSettings.from_mapping(values)
            ControlSettings.from_mapping(values)
        except ConfigurationError as error:
            parser.error(str(error))
        print("configuration=valid")
        print("source=.env+process-environment")
        print("secrets=redacted")
        return 0
    parser.error(f"Unsupported command: {arguments.command}")


def _add_audio_device_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--input-device",
        help="PortAudio input device name or numeric index (default: system input).",
    )
    command.add_argument(
        "--output-device",
        help="PortAudio output device name or numeric index (default: system output).",
    )


if __name__ == "__main__":
    raise SystemExit(main())
