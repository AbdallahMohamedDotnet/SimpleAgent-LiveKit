"""Aggregate the provider-free P10 acceptance smoke checks.

This command exercises only the workflows that are currently runnable without
credentials or physical audio devices. It must not be cited as evidence for the
blocked real-room, microphone, speaker, or provider acceptance gates.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str]) -> str:
    environment = dict(os.environ)
    for secret_name in (
        "OPENROUTER_API_KEY",
        "ELEVEN_API_KEY",
        "HR_VOICE_ID",
        "TECH_VOICE_ID",
    ):
        environment.pop(secret_name, None)
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Smoke command failed ({' '.join(command)}):\n{completed.stdout}{completed.stderr}"
        )
    return completed.stdout


def _run_json_script(name: str) -> dict[str, object]:
    output = _run([sys.executable, str(PROJECT_ROOT / "scripts" / name)])
    result = json.loads(output)
    if result.get("status") != "passed" or result.get("provider_request_made") is not False:
        raise RuntimeError(f"Unexpected result from {name}: {result}")
    return result


def main() -> None:
    dry_run = _run(
        [
            sys.executable,
            "-m",
            "interview_app.entrypoints.cli",
            "dry-run",
            "--name",
            "P10 Synthetic Candidate",
        ]
    )
    expected_dry_run_lines = {
        "state=interview_finished",
        "event=hr:started",
        "event=hr:draining",
        "event=hr:closed",
        "event=technical:started",
        "event=technical:draining",
        "event=technical:closed",
    }
    observed_lines = set(dry_run.splitlines())
    missing_lines = sorted(expected_dry_run_lines - observed_lines)
    if missing_lines:
        raise RuntimeError(f"Dry-run lifecycle output is incomplete: {missing_lines}")

    scoring = _run_json_script("p07_scoring_smoke.py")
    recovery_retention = _run_json_script("p08_recovery_retention_smoke.py")
    results = _run_json_script("p09_results_smoke.py")

    report = {
        "status": "passed",
        "scope": "offline_only",
        "dry_run": {
            "finished": True,
            "ordered_two_stage_lifecycle": True,
        },
        "scoring": {
            "task_state": scoring["task_state"],
            "restart_read_verified": scoring["restart_read_verified"],
        },
        "recovery": recovery_retention["recovery"],
        "retention": recovery_retention["retention"],
        "results": {
            "list_status": results["list_status"],
            "detail_status": results["detail_status"],
            "media_status": results["media_status"],
            "post_status": results["post_status"],
            "untrusted_html_escaped": bool(
                results["candidate_html_escaped"] and results["transcript_html_escaped"]
            ),
        },
        "provider_request_made": False,
        "live_audio_verified": False,
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
