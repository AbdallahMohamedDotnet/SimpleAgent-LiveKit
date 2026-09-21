"""Supervision of the local background service stack started from the interactive menu.

The startup policy itself stays in `scripts/run_local.sh`: this adapter owns one child process
and its shutdown, not the order in which LiveKit, the Agent Server and the scoring worker start.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

_STARTUP_OBSERVATION_SECONDS: Final = 4.0
_POLL_SECONDS: Final = 0.2


class ServiceStartError(RuntimeError):
    """Raised when the background service stack exits during startup."""


@dataclass(frozen=True, slots=True)
class ServiceStatus:
    """What this process knows about the stack; it cannot see services it did not start."""

    managed_here: bool
    pid: int | None
    livekit_reachable: bool


def is_port_open(url: str, *, timeout_seconds: float = 0.5) -> bool:
    """Report whether the host/port in a LiveKit URL currently accepts a TCP connection."""
    split = urlsplit(url)
    host = split.hostname
    port = split.port
    if host is None or port is None:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


class LocalServiceSupervisor:
    """Start and stop `scripts/run_local.sh` as one supervised child process."""

    def __init__(self, *, script: Path, log_path: Path, livekit_url: str) -> None:
        self._script = script
        self._log_path = log_path
        self._livekit_url = livekit_url
        self._process: subprocess.Popen[bytes] | None = None

    @property
    def log_path(self) -> Path:
        return self._log_path

    def status(self) -> ServiceStatus:
        process = self._live_process()
        return ServiceStatus(
            managed_here=process is not None,
            pid=process.pid if process is not None else None,
            livekit_reachable=is_port_open(self._livekit_url),
        )

    def start(self) -> ServiceStatus:
        """Start the stack, or return the current status when it is already running here."""
        if self._live_process() is not None:
            return self.status()
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("ab") as log:
            self._process = subprocess.Popen(
                [str(self._script), "--no-probe", "--skip-cleanup"],
                cwd=self._script.parent.parent,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                # Its own session, so a Ctrl-C in the menu does not reach the services.
                start_new_session=True,
            )
        self._observe_startup()
        return self.status()

    def stop(self, *, timeout_seconds: float = 30.0) -> None:
        """Ask the script to shut its own services down in order, then insist."""
        process = self._live_process()
        if process is None:
            self._process = None
            return
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            self._terminate_group(process)
            process.wait(timeout=timeout_seconds)
        finally:
            self._process = None

    def tail_log(self, *, lines: int = 20) -> str:
        try:
            content = self._log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return "\n".join(content.splitlines()[-lines:])

    def _observe_startup(self) -> None:
        deadline = time.monotonic() + _STARTUP_OBSERVATION_SECONDS
        while time.monotonic() < deadline:
            if self._live_process() is None:
                self._process = None
                raise ServiceStartError(
                    f"The service stack exited during startup. Last log lines:\n{self.tail_log()}"
                )
            if is_port_open(self._livekit_url):
                return
            time.sleep(_POLL_SECONDS)

    def _live_process(self) -> subprocess.Popen[bytes] | None:
        if self._process is None or self._process.poll() is not None:
            return None
        return self._process

    @staticmethod
    def _terminate_group(process: subprocess.Popen[bytes]) -> None:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except ProcessLookupError:
            return
