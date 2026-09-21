"""Human-readable terminal rendering of the read-only results projection."""

from __future__ import annotations

from datetime import UTC, datetime

from interview_app.adapters.terminal.sanitize import sanitize_block, sanitize_line
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

INDEPENDENCE_NOTE = (
    "HR and technical assessments are independent; no combined ranking or hiring "
    "recommendation is produced."
)


def render_interview_list(summaries: tuple[InterviewSummary, ...]) -> str:
    lines = [f"retained_interviews={len(summaries)}"]
    for summary in summaries:
        lines.append("")
        lines.extend(_summary_lines(summary))
    return "\n".join(lines)


def render_interview_detail(result: InterviewResult) -> str:
    lines = [
        f"interview_id={result.id}",
        f"candidate={sanitize_line(result.candidate_name)}",
        f"state={result.state.value}",
        f"created_at={_format_time(result.created_at)}",
        f"note={INDEPENDENCE_NOTE}",
    ]
    if not result.stages:
        lines.append("stages=none")
    for stage in result.stages:
        lines.append("")
        lines.extend(_stage_lines(stage))
    return "\n".join(lines)


def render_recording(record: MediaRecord, path: str) -> str:
    return "\n".join(
        (
            f"segment_id={record.segment_id}",
            f"status={record.status.value}",
            f"checksum_sha256={record.checksum_sha256}",
            f"path={sanitize_line(path)}",
            "player=not_started; open the file with a local audio player when needed.",
        )
    )


def render_mission(mission: InterviewMission) -> str:
    interview = mission.interview
    status = mission.status
    lines = [
        f"interview_id={interview.id}",
        f"candidate={sanitize_line(interview.candidate_name)}",
        f"state={interview.state.value}",
        f"room={sanitize_line(interview.room_name or 'none')}",
        f"room_available={_flag(status.room_available)}",
        f"dispatch_created={_flag(status.dispatch_created)}",
        f"agent_joined={_flag(status.agent_joined)}",
        f"candidate_joined={_flag(status.candidate_joined)}",
        f"transcript_turns={len(mission.transcript)}",
    ]
    for turn in mission.transcript:
        lines.append(
            f"  turn stage={turn.stage.value} speaker={turn.speaker.value} "
            f"delivery={turn.delivery_status.value} at={_format_time(turn.occurred_at)}"
        )
        lines.extend(_text_block(turn.text, indent=4))
    return "\n".join(lines)


def _summary_lines(summary: InterviewSummary) -> list[str]:
    lines = [
        f"interview_id={summary.id}",
        f"candidate={sanitize_line(summary.candidate_name)}",
        f"state={summary.state.value}",
        f"created_at={_format_time(summary.created_at)}",
    ]
    if not summary.stages:
        lines.append("  stages=none")
    lines.extend(f"  {_stage_summary_line(stage)}" for stage in summary.stages)
    return lines


def _stage_summary_line(stage: StageSummary) -> str:
    assessment = (
        stage.assessment_state.value if stage.assessment_state is not None else "not_started"
    )
    return (
        f"stage={stage.kind.value} conversation={stage.state.value} "
        f"assessment={assessment} "
        f"{_score_fields(stage.average, stage.assessed_count, stage.total_count)}"
    )


def _stage_lines(stage: StageResult) -> list[str]:
    lines = [
        f"stage={stage.kind.value}",
        f"  conversation={stage.state.value}",
    ]
    lines.extend(_assessment_lines(stage.assessment, {str(turn.id) for turn in stage.turns}))
    lines.append("  transcript:")
    if not stage.turns:
        lines.append("    (no finalized transcript turns)")
    for turn in stage.turns:
        lines.extend(_turn_lines(turn))
    lines.append("  recordings:")
    if not stage.recordings:
        lines.append("    (no recording segments)")
    for recording in stage.recordings:
        lines.extend(_recording_lines(recording))
    return lines


def _assessment_lines(assessment: AssessmentResult | None, turn_ids: set[str]) -> list[str]:
    if assessment is None:
        return ["  assessment=not_started"]
    lines = [
        f"  assessment={assessment.state.value}",
        f"  {_score_fields(assessment.average, assessment.assessed_count, assessment.total_count)}",
    ]
    if assessment.summary is None:
        lines.append("  summary=none")
    else:
        lines.append("  summary:")
        lines.extend(_text_block(assessment.summary, indent=4))
    if assessment.failure is not None:
        lines.append("  failure:")
        lines.extend(_text_block(assessment.failure, indent=4))
    if not assessment.competencies:
        lines.append("  competencies=none")
    for competency in assessment.competencies:
        lines.extend(_competency_lines(competency, turn_ids))
    return lines


def _competency_lines(competency: CompetencyResult, turn_ids: set[str]) -> list[str]:
    score = str(competency.score) if competency.score is not None else "unassessed"
    lines = [
        f"  competency={sanitize_line(competency.name)} "
        f"status={competency.status.value} score={score}",
        "    rationale:",
        *_text_block(competency.rationale, indent=6),
    ]
    lines.extend(_optional_block("limitation", competency.limitation))
    lines.extend(_optional_block("difficulty", competency.difficulty))
    lines.extend(_optional_block("assistance", competency.assistance))
    if not competency.evidence:
        lines.append("    evidence=none")
    for evidence in competency.evidence:
        identifier = str(evidence.turn_id)
        availability = "" if identifier in turn_ids else " (turn unavailable)"
        lines.append(f"    evidence turn={sanitize_line(identifier)}{availability}")
        lines.extend(_text_block(evidence.quote, indent=6))
    return lines


def _turn_lines(turn: ResultTurn) -> list[str]:
    return [
        f"    turn={turn.id} speaker={turn.speaker.value} "
        f"delivery={turn.delivery_status.value} at={_format_time(turn.occurred_at)}",
        *_text_block(turn.text, indent=6),
    ]


def _recording_lines(recording: RecordingResult) -> list[str]:
    lines = [
        f"    segment={recording.segment_id} speaker={recording.speaker.value} "
        f"status={recording.status.value} offset={recording.offset_seconds:.2f}s "
        f"duration={recording.duration_seconds:.2f}s",
    ]
    if recording.manifest_failure is not None:
        lines.append("      failure:")
        lines.extend(_text_block(recording.manifest_failure, indent=8))
    if not recording.gaps:
        lines.append("      gaps=none")
    for gap in recording.gaps:
        lines.append(
            f"      gap offset={gap.offset_seconds:.2f}s duration={gap.duration_seconds:.2f}s"
        )
        lines.extend(_text_block(gap.reason, indent=8))
    return lines


def _optional_block(label: str, value: str | None) -> list[str]:
    if value is None:
        return [f"    {label}=none"]
    return [f"    {label}:", *_text_block(value, indent=6)]


def _text_block(value: str, *, indent: int) -> list[str]:
    padding = " " * indent
    return [f"{padding}{line}" for line in sanitize_block(value).split("\n")]


def _score_fields(
    average: float | None, assessed_count: int | None, total_count: int | None
) -> str:
    if assessed_count is None or total_count is None:
        return "score=pending coverage=pending"
    average_text = f"{average:.2f}/5" if average is not None else "unassessed"
    return f"score={average_text} coverage={assessed_count}/{total_count}"


def _flag(value: bool) -> str:
    return "true" if value else "false"


def _format_time(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
