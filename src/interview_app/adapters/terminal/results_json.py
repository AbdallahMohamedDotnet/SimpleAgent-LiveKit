"""Stable machine-readable rendering of the read-only results projection.

JSON encoding already neutralizes control characters for consumers that decode it, so untrusted
text is emitted verbatim here instead of being escaped for a terminal.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from interview_app.application.launch import InterviewMission
from interview_app.application.results import (
    AssessmentResult,
    CompetencyResult,
    InterviewResult,
    InterviewSummary,
    MediaRecord,
    RecordingResult,
    ResultTurn,
    StageResult,
    StageSummary,
)


def render_interview_list(summaries: tuple[InterviewSummary, ...]) -> str:
    return _dump({"interviews": [_summary(summary) for summary in summaries]})


def render_interview_detail(result: InterviewResult) -> str:
    return _dump(
        {
            "interview_id": str(result.id),
            "candidate_name": result.candidate_name,
            "state": result.state.value,
            "created_at": _timestamp(result.created_at),
            "stages": [_stage(stage) for stage in result.stages],
        }
    )


def render_recording(record: MediaRecord, path: str) -> str:
    return _dump(
        {
            "segment_id": str(record.segment_id),
            "status": record.status.value,
            "checksum_sha256": record.checksum_sha256,
            "path": path,
        }
    )


def render_mission(mission: InterviewMission) -> str:
    return _dump(
        {
            "interview_id": str(mission.interview.id),
            "candidate_name": mission.interview.candidate_name,
            "state": mission.interview.state.value,
            "room_name": mission.interview.room_name,
            "room_available": mission.status.room_available,
            "dispatch_created": mission.status.dispatch_created,
            "agent_joined": mission.status.agent_joined,
            "candidate_joined": mission.status.candidate_joined,
            "transcript": [
                {
                    "stage": turn.stage.value,
                    "speaker": turn.speaker.value,
                    "delivery_status": turn.delivery_status.value,
                    "occurred_at": _timestamp(turn.occurred_at),
                    "text": turn.text,
                }
                for turn in mission.transcript
            ],
        }
    )


def _summary(summary: InterviewSummary) -> dict[str, Any]:
    return {
        "interview_id": str(summary.id),
        "candidate_name": summary.candidate_name,
        "state": summary.state.value,
        "created_at": _timestamp(summary.created_at),
        "stages": [_stage_summary(stage) for stage in summary.stages],
    }


def _stage_summary(stage: StageSummary) -> dict[str, Any]:
    return {
        "kind": stage.kind.value,
        "conversation_state": stage.state.value,
        "assessment_state": (
            stage.assessment_state.value if stage.assessment_state is not None else None
        ),
        "average": stage.average,
        "assessed_count": stage.assessed_count,
        "total_count": stage.total_count,
    }


def _stage(stage: StageResult) -> dict[str, Any]:
    return {
        "stage_id": str(stage.id),
        "kind": stage.kind.value,
        "conversation_state": stage.state.value,
        "assessment": _assessment(stage.assessment),
        "transcript": [_turn(turn) for turn in stage.turns],
        "recordings": [_recording(recording) for recording in stage.recordings],
    }


def _assessment(assessment: AssessmentResult | None) -> dict[str, Any] | None:
    if assessment is None:
        return None
    return {
        "state": assessment.state.value,
        "average": assessment.average,
        "assessed_count": assessment.assessed_count,
        "total_count": assessment.total_count,
        "summary": assessment.summary,
        "failure": assessment.failure,
        "competencies": [_competency(item) for item in assessment.competencies],
    }


def _competency(competency: CompetencyResult) -> dict[str, Any]:
    return {
        "name": competency.name,
        "status": competency.status.value,
        "score": competency.score,
        "rationale": competency.rationale,
        "limitation": competency.limitation,
        "difficulty": competency.difficulty,
        "assistance": competency.assistance,
        "evidence": [
            {"turn_id": str(evidence.turn_id), "quote": evidence.quote}
            for evidence in competency.evidence
        ],
    }


def _turn(turn: ResultTurn) -> dict[str, Any]:
    return {
        "turn_id": str(turn.id),
        "speaker": turn.speaker.value,
        "delivery_status": turn.delivery_status.value,
        "occurred_at": _timestamp(turn.occurred_at),
        "text": turn.text,
    }


def _recording(recording: RecordingResult) -> dict[str, Any]:
    return {
        "segment_id": str(recording.segment_id),
        "speaker": recording.speaker.value,
        "status": recording.status.value,
        "offset_seconds": recording.offset_seconds,
        "duration_seconds": recording.duration_seconds,
        "manifest_failure": recording.manifest_failure,
        "gaps": [
            {
                "offset_seconds": gap.offset_seconds,
                "duration_seconds": gap.duration_seconds,
                "reason": gap.reason,
            }
            for gap in recording.gaps
        ],
    }


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=False)
