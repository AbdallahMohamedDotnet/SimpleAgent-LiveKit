"""Interactive operator menu: one terminal surface for every application function."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from interview_app.adapters.livekit.candidate import (
    CandidateAudioUnavailableError,
    SoundDeviceBackend,
)
from interview_app.adapters.process import (
    LocalServiceSupervisor,
    ServiceStartError,
    ServiceStatus,
)
from interview_app.adapters.terminal.console import OperatorCancelled, StdConsole
from interview_app.adapters.terminal.sanitize import sanitize_line
from interview_app.application.interview import InvalidCandidateNameError
from interview_app.application.ports.interview_launch import InterviewLaunchError
from interview_app.application.ports.interview_store import (
    ActiveInterviewExistsError,
    InterviewNotFoundError,
    InterviewStateConflictError,
)
from interview_app.application.ports.results import ResultNotFoundError
from interview_app.application.results import InterviewSummary
from interview_app.bootstrap import build_dry_run_interview
from interview_app.domain.models import InterviewId, RecordingSegmentId
from interview_app.entrypoints.candidate import (
    ACTIVE_INTERVIEW_HINT,
    ensure_no_active_interview,
    join_existing,
    start_and_join,
)
from interview_app.entrypoints.cleanup import run_cleanup
from interview_app.entrypoints.environment import load_environment
from interview_app.entrypoints.results import (
    load_interview_result,
    load_interview_summaries,
    load_recording,
    render_recording,
    render_result,
    render_summaries,
)
from interview_app.entrypoints.status import run_status
from interview_app.settings import (
    CleanupSettings,
    ConfigurationError,
    LaunchSettings,
    ResultsSettings,
    Settings,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

# Failures an operator can act on without a traceback: bad configuration, a missing device, an
# unknown or expired record, or a refused launch. Programming defects still propagate.
_REPORTABLE_FAILURES = (
    CandidateAudioUnavailableError,
    ConfigurationError,
    InterviewLaunchError,
    InterviewNotFoundError,
    InterviewStateConflictError,
    InvalidCandidateNameError,
    ResultNotFoundError,
    ServiceStartError,
)


class Console(Protocol):
    """The only input/output this menu needs."""

    def write(self, message: str) -> None: ...

    def prompt(self, message: str) -> str: ...


class ServiceControl(Protocol):
    """The only background-service operations this menu needs."""

    @property
    def log_path(self) -> Path: ...

    def status(self) -> ServiceStatus: ...

    def start(self) -> ServiceStatus: ...

    def stop(self) -> None: ...


@dataclass(frozen=True, slots=True)
class MenuItem:
    key: str
    label: str
    action: Callable[[], None]


class InterviewMenu:
    """Present every command as a numbered choice and delegate to the existing use cases."""

    def __init__(self, *, console: Console, supervisor: ServiceControl) -> None:
        self._console = console
        self._supervisor = supervisor
        self._items = self._build_items()
        self._index: Mapping[str, MenuItem] = {item.key: item for item in self._items}

    def run(self) -> int:
        self._console.write(_BANNER)
        try:
            while True:
                self._console.write(self._render_menu())
                choice = self._console.prompt("Choose an option: ").strip()
                if choice in {"0", "q", "quit", "exit"}:
                    break
                self._dispatch(choice)
        except OperatorCancelled:
            self._console.write("\nInput closed; leaving the menu.")
        except KeyboardInterrupt:
            self._console.write("\nInterrupted; leaving the menu.")
        finally:
            self._shutdown_services()
        return 0

    def _dispatch(self, choice: str) -> None:
        item = self._index.get(choice)
        if item is None:
            self._console.write(f"Unknown option: {sanitize_line(choice)}")
            return
        try:
            item.action()
        except ActiveInterviewExistsError as error:
            self._console.write(f"error={error}\n{ACTIVE_INTERVIEW_HINT}")
            if self._supervisor.status().managed_here:
                self._console.write("From this menu: choose 2, then 1, then start the interview.")
        except _REPORTABLE_FAILURES as error:
            self._console.write(f"error={error}")
        except KeyboardInterrupt:
            self._console.write("\nStopped; returning to the menu.")

    def _build_items(self) -> tuple[MenuItem, ...]:
        return (
            MenuItem(
                "1",
                "Start background services (LiveKit, agent server, scoring worker)",
                self._start_services,
            ),
            MenuItem("2", "Stop background services", self._stop_services),
            MenuItem(
                "3",
                "Start a new interview (uses this terminal's microphone)",
                self._start_interview,
            ),
            MenuItem("4", "Rejoin an existing interview", self._rejoin_interview),
            MenuItem("5", "Show live interview status", self._show_status),
            MenuItem("6", "List retained interview results", self._list_results),
            MenuItem("7", "Show one interview's full results", self._show_results),
            MenuItem("8", "Locate a recording file", self._locate_recording),
            MenuItem("9", "List audio devices", self._list_devices),
            MenuItem("10", "Check configuration", self._check_configuration),
            MenuItem("11", "Run retention cleanup (deletes data past 30 days)", self._cleanup),
            MenuItem("12", "Offline dry run (no providers, no room, no audio)", self._dry_run),
        )

    def _render_menu(self) -> str:
        status = self._supervisor.status()
        lines = ["", _render_status(status), ""]
        lines.extend(f" {item.key:>2}) {item.label}" for item in self._items)
        lines.append("  0) Quit")
        return "\n".join(lines)

    # --- services -----------------------------------------------------------------

    def _start_services(self) -> None:
        status = self._supervisor.start()
        self._console.write(f"Services started. Logs: {self._supervisor.log_path}")
        self._console.write(_render_status(status))
        if not status.livekit_reachable:
            self._console.write(
                "LiveKit is not accepting connections yet; check the log if it stays closed."
            )

    def _stop_services(self) -> None:
        if not self._supervisor.status().managed_here:
            self._console.write("No services were started from this menu.")
            return
        self._console.write("Stopping services...")
        self._supervisor.stop()
        self._console.write("Services stopped.")

    def _shutdown_services(self) -> None:
        if self._supervisor.status().managed_here:
            self._console.write("Stopping the services this menu started...")
            self._supervisor.stop()

    # --- interview ----------------------------------------------------------------

    def _start_interview(self) -> None:
        if not self._supervisor.status().livekit_reachable:
            self._console.write(
                "LiveKit is not reachable. Start the background services (option 1) first."
            )
            return
        asyncio.run(ensure_no_active_interview(_launch_settings()))
        name = self._console.prompt("Candidate name: ").strip()
        if not name:
            self._console.write("A candidate name is required.")
            return
        devices = self._ask_devices()
        self._console.write("Connecting; press Ctrl-C to leave the interview.")
        asyncio.run(
            start_and_join(
                _launch_settings(),
                candidate_name=name,
                input_device=devices[0],
                output_device=devices[1],
            )
        )

    def _rejoin_interview(self) -> None:
        interview_id = self._ask_interview()
        if interview_id is None:
            return
        devices = self._ask_devices()
        self._console.write("Connecting; press Ctrl-C to leave the interview.")
        asyncio.run(
            join_existing(
                _launch_settings(),
                interview_id=interview_id,
                input_device=devices[0],
                output_device=devices[1],
            )
        )

    def _show_status(self) -> None:
        interview_id = self._ask_interview()
        if interview_id is None:
            return
        self._console.write(
            asyncio.run(run_status(_launch_settings(), interview_id, as_json=self._ask_json()))
        )

    # --- results ------------------------------------------------------------------

    def _list_results(self) -> None:
        summaries = asyncio.run(load_interview_summaries(_results_settings()))
        self._console.write(render_summaries(summaries, as_json=self._ask_json()))

    def _show_results(self) -> None:
        interview_id = self._ask_interview()
        if interview_id is None:
            return
        result = asyncio.run(load_interview_result(_results_settings(), interview_id))
        self._console.write(render_result(result, as_json=self._ask_json()))

    def _locate_recording(self) -> None:
        interview_id = self._ask_interview()
        if interview_id is None:
            return
        result = asyncio.run(load_interview_result(_results_settings(), interview_id))
        segments = tuple(recording for stage in result.stages for recording in stage.recordings)
        if not segments:
            self._console.write("This interview has no recording segments.")
            return
        labels = [
            f"{item.segment_id} ({item.speaker.value}, {item.status.value}, "
            f"{item.duration_seconds:.2f}s)"
            for item in segments
        ]
        chosen = self._choose("Recording", labels)
        if chosen is None:
            return
        record, path = asyncio.run(
            load_recording(
                _results_settings(), RecordingSegmentId(str(segments[chosen].segment_id))
            )
        )
        self._console.write(render_recording(record, path, as_json=False))

    # --- maintenance --------------------------------------------------------------

    def _list_devices(self) -> None:
        self._console.write(SoundDeviceBackend().devices())

    def _check_configuration(self) -> None:
        values = load_environment()
        Settings.from_mapping(values)
        LaunchSettings.from_mapping(values)
        ResultsSettings.from_mapping(values)
        CleanupSettings.from_mapping(values)
        self._console.write(
            "configuration=valid\nsource=.env+process-environment\nsecrets=redacted"
        )

    def _cleanup(self) -> None:
        self._console.write(
            "Cleanup permanently deletes interviews and recordings older than 30 days."
        )
        if self._console.prompt("Type 'delete' to confirm: ").strip() != "delete":
            self._console.write("Cleanup cancelled.")
            return
        report = asyncio.run(run_cleanup(CleanupSettings.from_mapping(load_environment())))
        self._console.write(
            f"cleanup_prepared={report.prepared}\n"
            f"cleanup_deleted={len(report.deleted)}\n"
            f"cleanup_failed={len(report.failed)}"
        )

    def _dry_run(self) -> None:
        name = self._console.prompt("Candidate name for the offline lifecycle: ").strip()
        result = asyncio.run(build_dry_run_interview().execute(name))
        events = "\n".join(
            f"event={event.stage_kind.value}:{event.type.value}" for event in result.events
        )
        self._console.write(
            f"interview_id={result.interview.id}\nstate={result.interview.state.value}\n{events}"
        )

    # --- shared questions ---------------------------------------------------------

    def _ask_interview(self) -> InterviewId | None:
        """Offer the retained interviews as a pick list, or accept a typed ID."""
        summaries = asyncio.run(load_interview_summaries(_results_settings()))
        if not summaries:
            self._console.write("No retained interviews. Enter an ID if you have one.")
            typed = self._console.prompt("Interview ID (blank to cancel): ").strip()
            return InterviewId(typed) if typed else None
        chosen = self._choose("Interview", [_summary_label(item) for item in summaries])
        if chosen is None:
            return None
        return summaries[chosen].id

    def _choose(self, subject: str, labels: list[str]) -> int | None:
        for position, label in enumerate(labels, start=1):
            self._console.write(f"  {position:>2}) {label}")
        answer = self._console.prompt(f"{subject} number (blank to cancel): ").strip()
        if not answer:
            return None
        if not answer.isdigit() or not 1 <= int(answer) <= len(labels):
            self._console.write(f"Not a listed {subject.lower()} number.")
            return None
        return int(answer) - 1

    def _ask_devices(self) -> tuple[str | None, str | None]:
        input_device = self._console.prompt("Input device (blank for default): ").strip()
        output_device = self._console.prompt("Output device (blank for default): ").strip()
        return (input_device or None, output_device or None)

    def _ask_json(self) -> bool:
        return self._console.prompt("Print JSON instead of a report? [y/N]: ").strip().lower() in {
            "y",
            "yes",
        }


_BANNER = """
Local Voice Interview — operator menu
Everything runs in this terminal. There is no web page to open.
"""


def _render_status(status: ServiceStatus) -> str:
    services = f"running (pid {status.pid})" if status.managed_here else "not started here"
    livekit = "reachable" if status.livekit_reachable else "unreachable"
    return f"services={services}  livekit={livekit}"


def _summary_label(summary: InterviewSummary) -> str:
    stages = " ".join(f"{stage.kind.value}:{stage.state.value}" for stage in summary.stages)
    return (
        f"{summary.id}  {sanitize_line(summary.candidate_name)}  [{summary.state.value}] {stages}"
    )


def _launch_settings() -> LaunchSettings:
    return LaunchSettings.from_mapping(load_environment())


def _results_settings() -> ResultsSettings:
    return ResultsSettings.from_mapping(load_environment())


def main() -> int:
    settings_values = load_environment()
    livekit_url = settings_values.get("LIVEKIT_URL", "ws://127.0.0.1:7880").strip()
    supervisor = LocalServiceSupervisor(
        script=REPOSITORY_ROOT / "scripts" / "run_local.sh",
        log_path=REPOSITORY_ROOT / "data" / "logs" / "menu-services.log",
        livekit_url=livekit_url,
    )
    return InterviewMenu(console=StdConsole(), supervisor=supervisor).run()


if __name__ == "__main__":
    raise SystemExit(main())
