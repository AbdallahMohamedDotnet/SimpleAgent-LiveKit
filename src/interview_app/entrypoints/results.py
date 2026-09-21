"""Read-only terminal results commands.

Loading and rendering are separate so the interactive menu can offer a pick list built from the
same DTOs the printed report uses, without a second query path.
"""

from __future__ import annotations

from pathlib import Path

from interview_app.adapters.artifacts import OwnedPathError
from interview_app.adapters.clock import SystemClock
from interview_app.adapters.terminal import results_json, results_text
from interview_app.application.ports.results import ResultNotFoundError
from interview_app.application.results import InterviewResult, InterviewSummary, MediaRecord
from interview_app.bootstrap import build_results_reader
from interview_app.domain.models import InterviewId, RecordingSegmentId
from interview_app.settings import ResultsSettings


async def load_interview_summaries(settings: ResultsSettings) -> tuple[InterviewSummary, ...]:
    database, reader, _ = build_results_reader(settings)
    await database.migrate()
    return await reader.list_interviews(now=SystemClock().utc_now())


async def load_interview_result(
    settings: ResultsSettings,
    interview_id: InterviewId,
) -> InterviewResult:
    database, reader, _ = build_results_reader(settings)
    await database.migrate()
    return await reader.get_interview(interview_id, now=SystemClock().utc_now())


async def load_recording(
    settings: ResultsSettings,
    segment_id: RecordingSegmentId,
) -> tuple[MediaRecord, Path]:
    database, reader, locator = build_results_reader(settings)
    await database.migrate()
    record = await reader.get_media(segment_id, now=SystemClock().utc_now())
    try:
        path = await locator.locate(record.relative_path)
    except OwnedPathError as error:
        # The record is authorized, so an unusable path is a missing or tampered recording
        # rather than an unknown ID; report it the same way to the operator.
        raise ResultNotFoundError(f"Recording {segment_id} is unavailable: {error}") from error
    return record, path


def render_summaries(summaries: tuple[InterviewSummary, ...], *, as_json: bool) -> str:
    if as_json:
        return results_json.render_interview_list(summaries)
    return results_text.render_interview_list(summaries)


def render_result(result: InterviewResult, *, as_json: bool) -> str:
    if as_json:
        return results_json.render_interview_detail(result)
    return results_text.render_interview_detail(result)


def render_recording(record: MediaRecord, path: Path, *, as_json: bool) -> str:
    if as_json:
        return results_json.render_recording(record, str(path))
    return results_text.render_recording(record, str(path))


async def run_results_list(settings: ResultsSettings, *, as_json: bool) -> str:
    return render_summaries(await load_interview_summaries(settings), as_json=as_json)


async def run_results_show(
    settings: ResultsSettings,
    interview_id: InterviewId,
    *,
    as_json: bool,
) -> str:
    return render_result(await load_interview_result(settings, interview_id), as_json=as_json)


async def run_results_recording(
    settings: ResultsSettings,
    segment_id: RecordingSegmentId,
    *,
    as_json: bool,
) -> str:
    record, path = await load_recording(settings, segment_id)
    return render_recording(record, path, as_json=as_json)
