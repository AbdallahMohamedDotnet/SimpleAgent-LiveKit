import json
from datetime import UTC, datetime

from interview_app.adapters.terminal import results_json, results_text
from interview_app.adapters.terminal.sanitize import sanitize_block, sanitize_line
from interview_app.application.launch import InterviewMission, MissionTranscriptTurn
from interview_app.application.ports.interview_launch import LaunchStatus
from interview_app.domain.models import (
    DeliveryStatus,
    InterviewId,
    InterviewRecord,
    InterviewState,
    Speaker,
    StageKind,
)

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
INJECTION = "\x1b[2K\rrm -rf /\x07\x9bB‮reversed​"


def test_sanitize_escapes_every_control_and_formatting_character() -> None:
    sanitized = sanitize_line(INJECTION)

    assert "\x1b" not in sanitized
    assert "\r" not in sanitized and "\x07" not in sanitized
    assert sanitized.startswith("\\x1b[2K\\x0drm -rf /\\x07\\x9bB")
    assert "\\u202e" in sanitized and "\\u200b" in sanitized
    # Ordinary text is untouched, so evidence stays readable.
    assert sanitize_line("Fully ordinary answer.") == "Fully ordinary answer."


def test_single_line_fields_cannot_forge_extra_report_lines() -> None:
    forged = "Alex\nstate=interview_finished"

    assert sanitize_line(forged) == "Alex\\nstate=interview_finished"
    assert sanitize_block(forged) == forged
    # A tab would still let content shift column alignment, so it is escaped in both modes.
    assert sanitize_block("a\tb") == "a\\x09b"


def _mission() -> InterviewMission:
    return InterviewMission(
        interview=InterviewRecord(
            id=InterviewId("mission-interview"),
            candidate_name=f"Alex {INJECTION}",
            state=InterviewState.HR_ACTIVE,
            created_at=NOW,
            room_name="interview-mission-interview",
            room_sid="RM_1",
            candidate_identity="candidate-1",
        ),
        status=LaunchStatus(
            room_available=True,
            dispatch_created=True,
            agent_joined=True,
            candidate_joined=False,
        ),
        transcript=(
            MissionTranscriptTurn(
                stage=StageKind.HR,
                speaker=Speaker.CANDIDATE,
                text=f"Answer {INJECTION}",
                delivery_status=DeliveryStatus.UNCERTAIN,
                occurred_at=NOW,
            ),
        ),
    )


def test_status_text_reports_room_dispatch_and_participants_safely() -> None:
    rendered = results_text.render_mission(_mission())

    assert "interview_id=mission-interview" in rendered
    assert "room=interview-mission-interview" in rendered
    assert "room_available=true" in rendered
    assert "dispatch_created=true" in rendered
    assert "agent_joined=true" in rendered
    assert "candidate_joined=false" in rendered
    assert "transcript_turns=1" in rendered
    assert "stage=hr speaker=candidate delivery=uncertain" in rendered
    assert "\x1b" not in rendered and "\x07" not in rendered


def test_status_json_keeps_untrusted_text_verbatim_for_scripts() -> None:
    payload = json.loads(results_json.render_mission(_mission()))

    assert payload["room_name"] == "interview-mission-interview"
    assert payload["candidate_joined"] is False
    assert payload["candidate_name"] == f"Alex {INJECTION}"
    assert payload["transcript"][0]["text"] == f"Answer {INJECTION}"
    assert payload["transcript"][0]["delivery_status"] == "uncertain"
