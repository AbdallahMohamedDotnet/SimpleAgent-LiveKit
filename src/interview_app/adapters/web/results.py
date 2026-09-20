"""Escaped server-rendered HTML and protected local recording delivery."""

from __future__ import annotations

import asyncio
import html
import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Final
from urllib.parse import quote, unquote, urlsplit

from interview_app.application.ports.clock import Clock
from interview_app.application.ports.results import ResultNotFoundError, ResultsReader
from interview_app.application.results import (
    AssessmentResult,
    CompetencyResult,
    InterviewResult,
    InterviewSummary,
    RecordingResult,
    StageResult,
    StageSummary,
)
from interview_app.domain.models import InterviewId, RecordingSegmentId, StageKind

_HTML_HEADERS: Final = {
    "Content-Type": "text/html; charset=utf-8",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; media-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: HTTPStatus
    body: bytes
    headers: dict[str, str]


class OwnedMediaReader:
    """Read only regular files resolved below the configured recording root."""

    def __init__(self, data_root: Path) -> None:
        self._data_root = data_root.resolve()

    async def read(self, relative_path: str) -> bytes:
        path = self._validate(relative_path)
        return await asyncio.to_thread(self._read_regular_file, path)

    def _validate(self, relative_path: str) -> Path:
        pure = PurePosixPath(relative_path)
        if pure.is_absolute() or not relative_path or ".." in pure.parts:
            raise FileNotFoundError("Media path is outside the owned recording root.")
        current = self._data_root
        for part in pure.parts:
            current = current / part
            if current.is_symlink():
                raise FileNotFoundError("Symbolic links are not served as media.")
        return current

    @staticmethod
    def _read_regular_file(path: Path) -> bytes:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        try:
            file_stat = os.fstat(descriptor)
            if not stat.S_ISREG(file_stat.st_mode):
                raise FileNotFoundError("Media is not a regular file.")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                return stream.read()
        finally:
            os.close(descriptor)


class ResultsHttpApplication:
    def __init__(self, *, reader: ResultsReader, recordings_root: Path, clock: Clock) -> None:
        self._reader = reader
        self._media = OwnedMediaReader(recordings_root)
        self._clock = clock

    async def handle(self, method: str, target: str) -> HttpResponse:
        if method not in {"GET", "HEAD"}:
            return _html_response(
                HTTPStatus.METHOD_NOT_ALLOWED,
                _page("Method not allowed", "<p>This viewer is read-only.</p>"),
                extra_headers={"Allow": "GET, HEAD"},
            )
        path = urlsplit(target).path
        try:
            if path == "/":
                return HttpResponse(
                    status=HTTPStatus.SEE_OTHER,
                    body=b"",
                    headers={"Location": "/results", "Cache-Control": "no-store"},
                )
            if path == "/results":
                results = await self._reader.list_interviews(now=self._clock.utc_now())
                response = _html_response(
                    HTTPStatus.OK,
                    _page("Interview results", _render_list(results)),
                )
            elif path.startswith("/results/") and path.count("/") == 2:
                identifier = unquote(path.removeprefix("/results/"))
                if not identifier:
                    raise ResultNotFoundError("Missing interview ID.")
                result = await self._reader.get_interview(
                    InterviewId(identifier), now=self._clock.utc_now()
                )
                response = _html_response(
                    HTTPStatus.OK,
                    _page(f"Results: {result.candidate_name}", _render_detail(result)),
                )
            elif path.startswith("/media/") and path.count("/") == 2:
                identifier = unquote(path.removeprefix("/media/"))
                if not identifier:
                    raise ResultNotFoundError("Missing media ID.")
                record = await self._reader.get_media(
                    RecordingSegmentId(identifier), now=self._clock.utc_now()
                )
                body = await self._media.read(record.relative_path)
                response = HttpResponse(
                    status=HTTPStatus.OK,
                    body=body,
                    headers={
                        "Content-Type": "audio/wav",
                        "Content-Length": str(len(body)),
                        "Content-Disposition": "inline",
                        "ETag": f'"{record.checksum_sha256}"',
                        "X-Content-Type-Options": "nosniff",
                        "Cache-Control": "no-store",
                    },
                )
            else:
                raise ResultNotFoundError("Unknown route.")
        except ResultNotFoundError, FileNotFoundError, OSError:
            response = _html_response(
                HTTPStatus.NOT_FOUND,
                _page("Not found", "<p>The result or recording is unavailable.</p>"),
            )
        if method == "HEAD":
            return HttpResponse(status=response.status, body=b"", headers=response.headers)
        return response


class ResultsHttpServer(ThreadingHTTPServer):
    application: ResultsHttpApplication


def create_results_server(
    application: ResultsHttpApplication,
    *,
    host: str,
    port: int,
) -> ResultsHttpServer:
    server = ResultsHttpServer((host, port), _ResultsHandler)
    server.application = application
    return server


class _ResultsHandler(BaseHTTPRequestHandler):
    server: ResultsHttpServer

    def do_GET(self) -> None:
        self._respond("GET")

    def do_HEAD(self) -> None:
        self._respond("HEAD")

    def do_POST(self) -> None:
        self._respond("POST")

    def _respond(self, method: str) -> None:
        response = asyncio.run(self.server.application.handle(method, self.path))
        self.send_response(response.status)
        for name, value in response.headers.items():
            self.send_header(name, value)
        if "Content-Length" not in response.headers:
            self.send_header("Content-Length", str(len(response.body)))
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(response.body)

    def log_message(self, format: str, *args: object) -> None:
        # Avoid putting candidate-controlled URLs into routine operator logs.
        return


def _render_list(results: tuple[InterviewSummary, ...]) -> str:
    if not results:
        return "<p>No retained interview results are available.</p>"
    cards: list[str] = []
    for result in results:
        stages = "".join(_render_stage_summary(stage) for stage in result.stages)
        if not stages:
            stages = '<p class="muted">No stages recorded.</p>'
        cards.append(
            '<article class="card">'
            f'<h2><a href="/results/{quote(str(result.id), safe="")}">'
            f"{_escape(result.candidate_name)}</a></h2>"
            f'<p><span class="badge">{_label(result.state.value)}</span> '
            f"{_escape(_format_time(result.created_at))}</p>"
            f'<div class="stage-grid">{stages}</div>'
            "</article>"
        )
    return (
        '<div class="toolbar"><p>Retained interviews, newest first.</p>'
        '<a class="button" href="/results">Refresh</a></div>' + "".join(cards)
    )


def _render_stage_summary(stage: StageSummary) -> str:
    assessment = (
        _label(stage.assessment_state.value)
        if stage.assessment_state is not None
        else "not started"
    )
    score = _score(stage.average, stage.assessed_count, stage.total_count)
    return (
        '<section class="stage-summary">'
        f"<h3>{_stage_name(stage.kind)}</h3>"
        f"<p>Conversation: {_label(stage.state.value)}</p>"
        f"<p>Assessment: {assessment}</p><p>{score}</p>"
        "</section>"
    )


def _render_detail(result: InterviewResult) -> str:
    stages = "".join(_render_stage(stage) for stage in result.stages)
    if not stages:
        stages = '<p class="muted">No stage evidence is available.</p>'
    return (
        '<p><a href="/results">← All results</a></p>'
        f"<h1>{_escape(result.candidate_name)}</h1>"
        f'<p><span class="badge">{_label(result.state.value)}</span> '
        f"Started {_escape(_format_time(result.created_at))}</p>"
        '<p class="notice">HR and technical assessments are independent. '
        "This viewer does not produce a combined ranking or hiring recommendation.</p>"
        f"{stages}"
    )


def _render_stage(stage: StageResult) -> str:
    turn_ids = {str(turn.id) for turn in stage.turns}
    assessment = _render_assessment(stage.assessment, turn_ids)
    transcript = "".join(
        f'<li id="turn-{html.escape(str(turn.id), quote=True)}"><strong>'
        f"{_label(turn.speaker.value)}</strong> "
        f'<span class="muted">({_label(turn.delivery_status.value)}, '
        f"{_escape(_format_time(turn.occurred_at))})</span><br>"
        f"{_escape(turn.text)}</li>"
        for turn in stage.turns
    )
    if not transcript:
        transcript = '<li class="muted">No finalized transcript turns.</li>'
    recordings = "".join(_render_recording(item) for item in stage.recordings)
    if not recordings:
        recordings = '<p class="muted">No recording segments are available.</p>'
    return (
        '<article class="stage card">'
        f"<h2>{_stage_name(stage.kind)}</h2>"
        f'<p>Conversation status: <span class="badge">{_label(stage.state.value)}</span></p>'
        f"{assessment}"
        "<h3>Transcript</h3>"
        f'<ol class="transcript">{transcript}</ol>'
        "<h3>Recordings and gaps</h3>"
        f"{recordings}</article>"
    )


def _render_assessment(
    assessment: AssessmentResult | None,
    turn_ids: set[str],
) -> str:
    if assessment is None:
        return '<section><h3>Assessment</h3><p class="muted">Not started.</p></section>'
    score = _score(
        assessment.average,
        assessment.assessed_count,
        assessment.total_count,
    )
    summary = (
        f"<p>{_escape(assessment.summary)}</p>"
        if assessment.summary is not None
        else '<p class="muted">No assessment summary.</p>'
    )
    failure = (
        f'<p class="error">Failure: {_escape(assessment.failure)}</p>'
        if assessment.failure is not None
        else ""
    )
    competencies = "".join(_render_competency(item, turn_ids) for item in assessment.competencies)
    if not competencies:
        competencies = '<p class="muted">Competency details are pending or unavailable.</p>'
    return (
        "<section><h3>Assessment</h3>"
        f'<p>Status: <span class="badge">{_label(assessment.state.value)}</span></p>'
        f"<p>{score}</p>{summary}{failure}{competencies}</section>"
    )


def _render_competency(
    competency: CompetencyResult,
    turn_ids: set[str],
) -> str:
    score = str(competency.score) if competency.score is not None else "unassessed"
    limitation = (
        f"<p><strong>Limitation:</strong> {_escape(competency.limitation)}</p>"
        if competency.limitation is not None
        else ""
    )
    difficulty = (
        f"<p><strong>Observed difficulty:</strong> {_escape(competency.difficulty)}</p>"
        if competency.difficulty is not None
        else '<p class="muted">Observed difficulty boundary not recorded.</p>'
    )
    assistance = (
        f"<p><strong>Hints/assistance:</strong> {_escape(competency.assistance)}</p>"
        if competency.assistance is not None
        else '<p class="muted">No hint or assistance detail recorded.</p>'
    )
    evidence_items: list[str] = []
    for evidence in competency.evidence:
        identifier = str(evidence.turn_id)
        link = (
            f'<a href="#turn-{html.escape(identifier, quote=True)}">turn {_escape(identifier)}</a>'
            if identifier in turn_ids
            else f"unavailable turn {_escape(identifier)}"
        )
        evidence_items.append(f"<li>{link}: “{_escape(evidence.quote)}”</li>")
    evidence_html = (
        f'<ul class="evidence">{"".join(evidence_items)}</ul>'
        if evidence_items
        else '<p class="muted">No numeric-score evidence.</p>'
    )
    return (
        '<section class="competency">'
        f"<h4>{_label(competency.name)} — {score}</h4>"
        f"<p>{_escape(competency.rationale)}</p>{limitation}{difficulty}{assistance}"
        f"{evidence_html}"
        "</section>"
    )


def _render_recording(recording: RecordingResult) -> str:
    gaps = "".join(
        f"<li>{gap.offset_seconds:.2f}s for {gap.duration_seconds:.2f}s: {_escape(gap.reason)}</li>"
        for gap in recording.gaps
    )
    gaps_html = f"<ul>{gaps}</ul>" if gaps else '<p class="muted">No declared gaps.</p>'
    failure = (
        f'<p class="error">Recording issue: {_escape(recording.manifest_failure)}</p>'
        if recording.manifest_failure is not None
        else ""
    )
    media_url = quote(str(recording.segment_id), safe="")
    return (
        '<section class="recording">'
        f"<p><strong>{_label(recording.speaker.value)}</strong> — "
        f"{_label(recording.status.value)}, {recording.duration_seconds:.2f}s at "
        f"{recording.offset_seconds:.2f}s</p>"
        f'<audio controls preload="none" src="/media/{media_url}">Recording unavailable.</audio>'
        f"{failure}{gaps_html}</section>"
    )


def _score(
    average: float | None,
    assessed_count: int | None,
    total_count: int | None,
) -> str:
    if assessed_count is None or total_count is None:
        return "Score: pending; coverage: pending"
    average_text = f"{average:.2f}/5" if average is not None else "unassessed"
    return f"Score: {average_text}; coverage: {assessed_count}/{total_count}"


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{_escape(title)}</title><style>
:root {{ color-scheme: light dark; font-family: system-ui, sans-serif; line-height: 1.5; }}
body {{ max-width: 72rem; margin: 0 auto; padding: 1.5rem; }}
a {{ color: #4f8cff; }} .toolbar {{ display:flex; justify-content:space-between; gap:1rem; }}
.card {{ border:1px solid #7777; border-radius:.6rem; padding:1rem; margin:1rem 0; }}
.stage-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(15rem,1fr)); gap:.8rem; }}
.stage-summary,.competency,.recording {{ border-left:.25rem solid #7777; padding-left:.8rem;
margin:1rem 0; }}
.badge,.button {{ border:1px solid #7777; border-radius:99rem; padding:.15rem .55rem; }}
.button {{ text-decoration:none; align-self:center; }} .muted {{ opacity:.72; }}
.notice {{ border-left:.25rem solid #4f8cff; padding:.7rem; }} .error {{ color:#d44; }}
.transcript li {{ margin-bottom:.8rem; }} audio {{ width:min(100%,32rem); }}
</style></head><body>{body}</body></html>"""


def _html_response(
    status: HTTPStatus,
    document: str,
    *,
    extra_headers: dict[str, str] | None = None,
) -> HttpResponse:
    body = document.encode("utf-8")
    headers = {**_HTML_HEADERS, "Content-Length": str(len(body))}
    if extra_headers is not None:
        headers.update(extra_headers)
    return HttpResponse(status=status, body=body, headers=headers)


def _escape(value: str) -> str:
    return html.escape(value, quote=True)


def _label(value: str) -> str:
    return _escape(value.replace("_", " ").title())


def _stage_name(kind: StageKind) -> str:
    return "HR" if kind is StageKind.HR else "Technical"


def _format_time(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
