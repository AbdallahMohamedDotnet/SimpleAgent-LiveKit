"""Operator command-line interface."""

import argparse
import asyncio
import sys
from collections.abc import Sequence
from typing import Final

from interview_app.adapters.livekit.candidate import (
    CandidateAudioUnavailableError,
    SoundDeviceBackend,
)
from interview_app.application.interview import InvalidCandidateNameError
from interview_app.application.ports.interview_store import (
    ActiveInterviewExistsError,
    InterviewNotFoundError,
)
from interview_app.application.ports.results import ResultNotFoundError
from interview_app.bootstrap import build_dry_run_interview
from interview_app.domain.models import InterviewId, RecordingSegmentId
from interview_app.entrypoints.candidate import (
    ACTIVE_INTERVIEW_HINT,
    join_existing,
    start_and_join,
)
from interview_app.entrypoints.cleanup import run_cleanup
from interview_app.entrypoints.environment import load_environment
from interview_app.entrypoints.results import (
    run_results_list,
    run_results_recording,
    run_results_show,
)
from interview_app.entrypoints.status import run_status
from interview_app.entrypoints.worker import run_worker
from interview_app.settings import (
    CleanupSettings,
    ConfigurationError,
    LaunchSettings,
    ResultsSettings,
    ScoringSettings,
    Settings,
)

EXIT_OK: Final = 0
EXIT_OPERATION_FAILED: Final = 1
EXIT_NOT_FOUND: Final = 3


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
    status = commands.add_parser(
        "status", help="Show room, agent dispatch and transcript status for one interview."
    )
    status.add_argument("--interview-id", required=True, help="Generated interview ID.")
    _add_json_argument(status)
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
        "cleanup",
        help="Delete interviews and owned artifacts whose 30-day retention has expired.",
    )
    _add_results_commands(commands)
    commands.add_parser(
        "config-check",
        help="Validate every .env setting without printing secret values.",
    )
    return parser


def _add_results_commands(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    results = commands.add_parser(
        "results", help="Read retained interview results in the terminal."
    )
    subcommands = results.add_subparsers(dest="results_command", required=True)
    listing = subcommands.add_parser("list", help="List retained interviews, newest first.")
    _add_json_argument(listing)
    show = subcommands.add_parser(
        "show", help="Show independent HR and technical evidence for one interview."
    )
    show.add_argument("--interview-id", required=True, help="Generated interview ID.")
    _add_json_argument(show)
    recording = subcommands.add_parser(
        "recording", help="Resolve one retained recording segment to its owned local file."
    )
    recording.add_argument("--segment-id", required=True, help="Recording segment ID.")
    _add_json_argument(recording)


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
        return EXIT_OK
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
        return EXIT_OK
    if arguments.command in {"run", "join"}:
        try:
            launch_settings = LaunchSettings.from_mapping(load_environment())
            if arguments.command == "run":
                asyncio.run(
                    start_and_join(
                        launch_settings,
                        candidate_name=arguments.name,
                        input_device=arguments.input_device,
                        output_device=arguments.output_device,
                    )
                )
            else:
                asyncio.run(
                    join_existing(
                        launch_settings,
                        interview_id=InterviewId(arguments.interview_id),
                        input_device=arguments.input_device,
                        output_device=arguments.output_device,
                    )
                )
        except (CandidateAudioUnavailableError, ConfigurationError) as error:
            parser.error(str(error))
        except ActiveInterviewExistsError as error:
            print(f"error={error}\nhint={ACTIVE_INTERVIEW_HINT}", file=sys.stderr)
            return EXIT_OPERATION_FAILED
        except InterviewNotFoundError as error:
            return _report_missing(error)
        except KeyboardInterrupt:
            print("candidate_audio=disconnected")
        return EXIT_OK
    if arguments.command == "status":
        try:
            launch_settings = LaunchSettings.from_mapping(load_environment())
            print(
                asyncio.run(
                    run_status(
                        launch_settings,
                        InterviewId(arguments.interview_id),
                        as_json=bool(arguments.json),
                    )
                )
            )
        except ConfigurationError as error:
            parser.error(str(error))
        except (InterviewNotFoundError, ResultNotFoundError) as error:
            return _report_missing(error)
        return EXIT_OK
    if arguments.command == "devices":
        try:
            print(SoundDeviceBackend().devices())
        except CandidateAudioUnavailableError as error:
            parser.error(str(error))
        return EXIT_OK
    if arguments.command == "cleanup":
        try:
            cleanup_settings = CleanupSettings.from_mapping(load_environment())
            report = asyncio.run(run_cleanup(cleanup_settings))
        except ConfigurationError as error:
            parser.error(str(error))
        print(f"cleanup_prepared={report.prepared}")
        print(f"cleanup_deleted={len(report.deleted)}")
        print(f"cleanup_failed={len(report.failed)}")
        return EXIT_OPERATION_FAILED if report.failed else EXIT_OK
    if arguments.command == "results":
        return _run_results_command(parser, arguments)
    if arguments.command == "config-check":
        try:
            values = load_environment()
            Settings.from_mapping(values)
            ScoringSettings.from_mapping(values)
            CleanupSettings.from_mapping(values)
            ResultsSettings.from_mapping(values)
            LaunchSettings.from_mapping(values)
        except ConfigurationError as error:
            parser.error(str(error))
        print("configuration=valid")
        print("source=.env+process-environment")
        print("secrets=redacted")
        return EXIT_OK
    parser.error(f"Unsupported command: {arguments.command}")


def _run_results_command(parser: argparse.ArgumentParser, arguments: argparse.Namespace) -> int:
    as_json = bool(arguments.json)
    try:
        settings = ResultsSettings.from_mapping(load_environment())
    except ConfigurationError as error:
        parser.error(str(error))
    try:
        if arguments.results_command == "list":
            output = asyncio.run(run_results_list(settings, as_json=as_json))
        elif arguments.results_command == "show":
            output = asyncio.run(
                run_results_show(
                    settings,
                    InterviewId(arguments.interview_id),
                    as_json=as_json,
                )
            )
        else:
            output = asyncio.run(
                run_results_recording(
                    settings,
                    RecordingSegmentId(arguments.segment_id),
                    as_json=as_json,
                )
            )
    except ResultNotFoundError as error:
        return _report_missing(error)
    print(output)
    return EXIT_OK


def _report_missing(error: Exception) -> int:
    # Untrusted content never reaches this message: it carries only the requested identifier,
    # which argparse received from the operator.
    print(f"error={error}", file=sys.stderr)
    return EXIT_NOT_FOUND


def _add_json_argument(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--json",
        action="store_true",
        help="Print stable JSON instead of the human-readable terminal report.",
    )


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
