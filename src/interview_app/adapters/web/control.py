"""Local operator pages for launching and observing interview missions."""

# ruff: noqa: E501 -- Embedded HTML/CSS is kept readable as rendered source.

from __future__ import annotations

import asyncio
import html
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Final
from urllib.parse import parse_qs, quote, unquote, urlsplit

from interview_app.application.interview import InvalidCandidateNameError
from interview_app.application.launch import (
    GetInterviewMission,
    InterviewMission,
    MissionTranscriptTurn,
    StartInterview,
)
from interview_app.application.ports.interview_launch import InterviewLaunchError
from interview_app.application.ports.interview_store import (
    InterviewNotFoundError,
    InterviewStateConflictError,
)
from interview_app.domain.models import InterviewId

from .results import HttpResponse

_MAX_FORM_BYTES: Final = 4096
_HTML_HEADERS: Final = {
    "Content-Type": "text/html; charset=utf-8",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
        "base-uri 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


class ControlHttpApplication:
    """Presentation-only HTTP boundary; launch policy stays in application use cases."""

    def __init__(
        self,
        *,
        start_interview: StartInterview,
        get_mission: GetInterviewMission,
        csrf_token: str | None = None,
    ) -> None:
        self._start_interview = start_interview
        self._get_mission = get_mission
        self._csrf_token = csrf_token or secrets.token_urlsafe(32)

    async def handle(
        self,
        method: str,
        target: str,
        *,
        body: bytes = b"",
        content_type: str = "",
    ) -> HttpResponse:
        path = urlsplit(target).path
        if method in {"GET", "HEAD"}:
            response = await self._read(path)
        elif method == "POST" and path == "/interviews":
            response = await self._start(body, content_type)
        else:
            response = _response(
                HTTPStatus.METHOD_NOT_ALLOWED,
                _page("Method not allowed", "<p>This action is not available.</p>"),
                extra_headers={"Allow": "GET, HEAD, POST"},
            )
        if method == "HEAD":
            return HttpResponse(response.status, b"", response.headers)
        return response

    async def _read(self, path: str) -> HttpResponse:
        if path == "/":
            return HttpResponse(
                HTTPStatus.SEE_OTHER,
                b"",
                {"Location": "/interviews/", "Cache-Control": "no-store"},
            )
        if path in {"/interviews", "/interviews/"}:
            return HttpResponse(
                HTTPStatus.SEE_OTHER,
                b"",
                {"Location": "/interviews/new", "Cache-Control": "no-store"},
            )
        if path == "/interviews/new":
            return _response(
                HTTPStatus.OK,
                _page("Start interview", _render_start_form(self._csrf_token)),
            )
        if path.startswith("/interviews/") and path.count("/") == 2:
            identifier = unquote(path.removeprefix("/interviews/"))
            try:
                mission = await self._get_mission.execute(InterviewId(identifier))
            except InterviewNotFoundError:
                return _not_found()
            except InterviewLaunchError as error:
                return _response(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    _page("Interview status unavailable", _render_error(str(error))),
                )
            return _response(
                HTTPStatus.OK,
                _page(
                    f"Interview: {mission.interview.candidate_name}",
                    _render_mission(mission),
                ),
                extra_headers={"Refresh": "2"},
            )
        return _not_found()

    async def _start(self, body: bytes, content_type: str) -> HttpResponse:
        if len(body) > _MAX_FORM_BYTES:
            return _response(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                _page("Form too large", _render_error("The submitted form is too large.")),
            )
        if content_type.split(";", 1)[0].strip() != "application/x-www-form-urlencoded":
            return _response(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                _page("Unsupported form", _render_error("Submit the interview form normally.")),
            )
        try:
            fields = parse_qs(body.decode("utf-8"), keep_blank_values=True, strict_parsing=True)
        except UnicodeDecodeError, ValueError:
            return _response(
                HTTPStatus.BAD_REQUEST,
                _page("Invalid form", _render_error("The submitted form is invalid.")),
            )
        token = fields.get("csrf_token", [""])[0]
        if not secrets.compare_digest(token, self._csrf_token):
            return _response(
                HTTPStatus.FORBIDDEN,
                _page("Request rejected", _render_error("Reload the form and try again.")),
            )
        candidate_name = fields.get("candidate_name", [""])[0]
        try:
            started = await self._start_interview.execute(candidate_name)
        except InvalidCandidateNameError as error:
            return _response(
                HTTPStatus.BAD_REQUEST,
                _page(
                    "Start interview",
                    _render_start_form(self._csrf_token, error=str(error), value=candidate_name),
                ),
            )
        except InterviewStateConflictError:
            return _response(
                HTTPStatus.CONFLICT,
                _page(
                    "Interview already active",
                    _render_error(
                        "Finish or recover the active interview before starting another one."
                    ),
                ),
            )
        except InterviewLaunchError as error:
            return _response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                _page("Interview could not start", _render_error(str(error))),
            )
        location = f"/interviews/{quote(str(started.interview.id), safe='')}"
        return HttpResponse(
            HTTPStatus.SEE_OTHER,
            b"",
            {"Location": location, "Cache-Control": "no-store"},
        )


class ControlHttpServer(ThreadingHTTPServer):
    application: ControlHttpApplication


def create_control_server(
    application: ControlHttpApplication,
    *,
    host: str,
    port: int,
) -> ControlHttpServer:
    server = ControlHttpServer((host, port), _ControlHandler)
    server.application = application
    return server


class _ControlHandler(BaseHTTPRequestHandler):
    server: ControlHttpServer

    def do_GET(self) -> None:
        self._respond("GET")

    def do_HEAD(self) -> None:
        self._respond("HEAD")

    def do_POST(self) -> None:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            length = _MAX_FORM_BYTES + 1
        body = self.rfile.read(min(max(length, 0), _MAX_FORM_BYTES + 1))
        self._respond("POST", body=body)

    def _respond(self, method: str, *, body: bytes = b"") -> None:
        response = asyncio.run(
            self.server.application.handle(
                method,
                self.path,
                body=body,
                content_type=self.headers.get("Content-Type", ""),
            )
        )
        self.send_response(response.status)
        for name, value in response.headers.items():
            self.send_header(name, value)
        if "Content-Length" not in response.headers:
            self.send_header("Content-Length", str(len(response.body)))
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(response.body)

    def log_message(self, format: str, *args: object) -> None:
        return


def _render_start_form(token: str, *, error: str | None = None, value: str = "") -> str:
    error_html = f'<p class="alert">{_escape(error)}</p>' if error else ""
    return (
        '<header class="mast"><div><p class="eyebrow">Operator console</p>'
        "<h1>Start a voice interview</h1>"
        '<p class="lede">Create the local room and dispatch the interview agent. '
        "Candidate audio remains in the terminal client.</p></div>"
        '<div class="mission-mark" aria-hidden="true"><span>HR</span><i></i><span>TECH</span></div>'
        "</header>"
        '<main class="layout"><section class="panel launch-panel">'
        '<p class="step">New mission</p><h2>Candidate details</h2>'
        f"{error_html}"
        '<form action="/interviews" method="post">'
        f'<input type="hidden" name="csrf_token" value="{_escape(token)}">'
        '<label for="candidate_name">Candidate name</label>'
        f'<input id="candidate_name" name="candidate_name" value="{_escape(value)}" '
        'maxlength="120" autocomplete="off" required autofocus>'
        '<p class="hint">Used for the operator record only; room and participant identities are generated.</p>'
        f'<button type="submit">{_microphone_icon()}<span>Start interview</span>'
        '<span aria-hidden="true">→</span></button>'
        "</form></section>"
        '<aside class="panel checklist"><p class="step">Before launch</p>'
        "<h2>Services ready</h2><ol>"
        "<li><div><strong>LiveKit server</strong><span>Local room service is running</span></div></li>"
        "<li><div><strong>Interview agent</strong><span>Running as interview-agent</span></div></li>"
        "<li><div><strong>Candidate terminal</strong><span>Connect after launch</span></div></li>"
        "</ol></aside></main>"
    )


def _render_mission(mission: InterviewMission) -> str:
    interview = mission.interview
    status = mission.status
    statuses = (
        ("Room", status.room_available, "Created", "Unavailable"),
        ("Agent dispatch", status.dispatch_created, "Sent", "Waiting"),
        ("Interview agent", status.agent_joined, "Joined", "Waiting"),
        ("Candidate audio", status.candidate_joined, "Connected", "Not connected"),
    )
    cards = "".join(
        '<li class="status-card">'
        + (
            f'<span class="mic-status {"ready" if ready else "waiting"}" '
            f'title="Microphone {"connected" if ready else "not connected"}">'
            f"{_microphone_icon()}</span>"
            if label == "Candidate audio"
            else f'<span class="status-dot {"ready" if ready else "waiting"}" '
            'aria-hidden="true"></span>'
        )
        + f"<div><strong>{_escape(label)}</strong>"
        f"<span>{_escape(ready_label if ready else waiting_label)}</span></div></li>"
        for label, ready, ready_label, waiting_label in statuses
    )
    ready = status.agent_joined and status.candidate_joined
    banner_class = "ready-banner" if ready else "waiting-banner"
    banner_title = "Interview can begin" if ready else "Waiting for participants"
    banner_text = (
        "The agent job and candidate terminal are both attached to this room."
        if ready
        else "Keep the agent server running, then connect the candidate terminal to this room."
    )
    room_name = interview.room_name or "Unavailable"
    candidate_identity = interview.candidate_identity or "Unavailable"
    join_command = (
        'LD_LIBRARY_PATH="$PWD/.tools/portaudio/usr/lib/x86_64-linux-gnu" '
        "UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview join "
        f'--interview-id "{interview.id}"'
    )
    transcript = _render_transcript(mission.transcript)
    return (
        '<header class="mission-header"><div><a class="back" href="/interviews/new">'
        "← New interview</a>"
        '<p class="eyebrow">Active mission</p>'
        f"<h1>{_escape(interview.candidate_name)}</h1>"
        f'<p class="mono">{_escape(str(interview.id))}</p></div>'
        f'<div class="{banner_class}"><strong>{banner_title}</strong><span>{banner_text}</span></div>'
        "</header>"
        '<main class="mission-layout"><section class="panel"><div class="section-head">'
        '<div><p class="step">Connection status</p><h2>Room readiness</h2></div>'
        f'<a class="refresh" href="/interviews/{quote(str(interview.id), safe="")}">Refresh</a>'
        f'</div><ul class="status-grid">{cards}</ul></section>'
        '<aside class="panel details"><p class="step">Terminal handoff</p>'
        f'<h2 class="with-icon">{_microphone_icon()} Connect microphone</h2>'
        "<dl><dt>Room</dt>"
        f"<dd><code>{_escape(room_name)}</code></dd>"
        "<dt>Candidate identity</dt>"
        f"<dd><code>{_escape(candidate_identity)}</code></dd>"
        "<dt>Room SID</dt>"
        f"<dd><code>{_escape(interview.room_sid or 'Pending')}</code></dd></dl>"
        '<p class="note">Run this from the project directory to attach the candidate microphone '
        "and speaker to this interview:</p>"
        f'<code class="join-command">{_escape(join_command)}</code>'
        '<p class="note">The microphone icon above turns green when the terminal audio client '
        "is connected. Keep that terminal open for the full interview.</p></aside>"
        f"{transcript}</main>"
    )


def _render_transcript(turns: tuple[MissionTranscriptTurn, ...]) -> str:
    if not turns:
        body = (
            '<p class="empty-transcript">Finalized speech will appear here after the candidate '
            "and interview agent begin talking.</p>"
        )
    else:
        body = '<ol class="turns">' + "".join(_render_turn(turn) for turn in turns) + "</ol>"
    return (
        '<section class="panel transcript"><div class="section-head"><div>'
        '<p class="step">Live evidence</p><h2>Interview transcript</h2></div>'
        '<span class="polling">Updates every 2 seconds</span></div>'
        f"{body}</section>"
    )


def _render_turn(turn: MissionTranscriptTurn) -> str:
    speaker = "Candidate" if turn.speaker.value == "candidate" else "Interviewer"
    timestamp = turn.occurred_at.astimezone().strftime("%H:%M:%S")
    return (
        f'<li class="turn {turn.speaker.value}"><div class="turn-meta">'
        f"<strong>{_escape(speaker)}</strong><span>{_escape(turn.stage.value.upper())}</span>"
        f"<time>{_escape(timestamp)}</time></div><p>{_escape(turn.text)}</p></li>"
    )


def _render_error(message: str) -> str:
    return (
        '<main class="single"><section class="panel"><p class="step">Action required</p>'
        f'<h1>Unable to continue</h1><p class="alert">{_escape(message)}</p>'
        '<a class="button" href="/interviews/new">Return to launch</a></section></main>'
    )


def _microphone_icon() -> str:
    return (
        '<svg class="mic-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
        '<path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Z"/>'
        '<path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6"/></svg>'
    )


def _not_found() -> HttpResponse:
    return _response(
        HTTPStatus.NOT_FOUND,
        _page("Not found", _render_error("The requested interview is unavailable.")),
    )


def _response(
    status: HTTPStatus,
    document: str,
    *,
    extra_headers: dict[str, str] | None = None,
) -> HttpResponse:
    body = document.encode("utf-8")
    headers = dict(_HTML_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    headers["Content-Length"] = str(len(body))
    return HttpResponse(status, body, headers)


def _page(title: str, content: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{_escape(title)} · Interview Console</title>"
        f'<style>{_styles()}</style></head><body><div class="shell">{content}</div></body></html>'
    )


def _styles() -> str:
    return """
:root{color-scheme:dark;--ink:#f7f8fa;--muted:#9ca5b5;--panel:#121722;--line:#293142;
--accent:#ffb84d;--accent-2:#78e8c6;--danger:#ff8585;--bg:#090c12}*{box-sizing:border-box}
body{margin:0;min-width:320px;background:radial-gradient(circle at 75% 0,#182033 0,transparent 38%),
var(--bg);color:var(--ink);font:16px/1.55 Inter,ui-sans-serif,system-ui,sans-serif}
.shell{width:min(1120px,calc(100% - 32px));margin:auto;padding:48px 0 64px}.mast,.mission-header{
display:flex;justify-content:space-between;gap:32px;align-items:flex-end;margin-bottom:32px}.eyebrow,.step{
margin:0 0 10px;color:var(--accent);font-size:.78rem;font-weight:800;letter-spacing:.14em;text-transform:uppercase}
h1{font-size:clamp(2.25rem,6vw,4.75rem);line-height:.95;letter-spacing:-.055em;margin:0;max-width:760px}
h2{font-size:1.35rem;margin:0 0 20px}.lede{color:var(--muted);font-size:1.08rem;max-width:620px;margin:20px 0 0}
.mission-mark{display:flex;align-items:center;gap:12px;font-weight:900;letter-spacing:.06em}.mission-mark span{
display:grid;place-items:center;width:66px;height:66px;border:1px solid var(--line);border-radius:50%;background:#111722}
.mission-mark i{width:52px;height:1px;background:linear-gradient(90deg,var(--accent),var(--accent-2))}
.layout,.mission-layout{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(300px,.75fr);gap:20px}.panel{
background:linear-gradient(145deg,rgba(22,29,43,.98),rgba(13,17,25,.98));border:1px solid var(--line);
border-radius:20px;padding:28px;box-shadow:0 24px 80px rgba(0,0,0,.2)}label{display:block;font-weight:750;margin-bottom:9px}
input{width:100%;border:1px solid #3a455b;border-radius:12px;background:#090d15;color:var(--ink);font:inherit;
font-size:1.05rem;padding:15px 16px;outline:none}input:focus{border-color:var(--accent);box-shadow:0 0 0 3px #ffb84d22}
.hint,.note{color:var(--muted);font-size:.9rem}.hint{margin:9px 0 24px}button,.button,.refresh{display:inline-flex;
align-items:center;justify-content:center;gap:14px;border:0;border-radius:12px;background:var(--accent);color:#211402;
font:inherit;font-weight:850;padding:14px 18px;text-decoration:none;cursor:pointer}button{width:100%}button:hover,.button:hover{background:#ffc66f}
.mic-icon{width:1.25rem;height:1.25rem;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;
stroke-linejoin:round}.with-icon{display:flex;align-items:center;gap:10px}.with-icon .mic-icon{color:var(--accent)}
.checklist ol{list-style:none;padding:0;margin:0}.checklist li{display:grid;grid-template-columns:28px 1fr;gap:12px;padding:14px 0;
border-top:1px solid var(--line)}.checklist li:before{content:'✓';color:var(--accent-2);font-weight:900}.checklist span,.status-card span{
display:block;color:var(--muted);font-size:.88rem}.back{display:inline-block;color:var(--muted);margin-bottom:28px;text-decoration:none}.mono,code{
font-family:ui-monospace,SFMono-Regular,Consolas,monospace}.mono{color:var(--muted);font-size:.82rem;margin:14px 0 0}
.waiting-banner,.ready-banner{max-width:360px;border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:14px;
padding:15px 18px;background:#111620}.ready-banner{border-left-color:var(--accent-2)}.waiting-banner span,.ready-banner span{
display:block;color:var(--muted);font-size:.86rem;margin-top:4px}.section-head{display:flex;align-items:center;justify-content:space-between;gap:20px}
.refresh{background:transparent;color:var(--ink);border:1px solid var(--line);padding:9px 13px}.status-grid{display:grid;
grid-template-columns:1fr 1fr;list-style:none;padding:0;margin:0;gap:12px}.status-card{display:flex;gap:12px;align-items:center;
border:1px solid var(--line);border-radius:14px;padding:16px;background:#0d121b}.status-dot{flex:0 0 auto;width:10px;height:10px;
border-radius:50%;background:#667085;box-shadow:0 0 0 5px #66708518}.status-dot.ready{background:var(--accent-2);
box-shadow:0 0 0 5px #78e8c618}.details dl{margin:0}.details dt{color:var(--muted);font-size:.78rem;text-transform:uppercase;
letter-spacing:.1em;margin-top:15px}.details dd{margin:5px 0;overflow-wrap:anywhere}.details code{color:#d8e2f2;font-size:.83rem}
.mic-status{display:grid!important;place-items:center;flex:0 0 auto;width:36px;height:36px;border-radius:50%;color:#9ca5b5;
background:#66708518;border:1px solid #66708555}.mic-status.ready{color:var(--accent-2);background:#78e8c618;border-color:#78e8c655}
.mic-status .mic-icon{width:18px;height:18px}.join-command{display:block;margin:10px 0 16px;padding:12px;border:1px solid var(--line);
border-radius:10px;background:#090d15;white-space:normal;overflow-wrap:anywhere;user-select:all}
.alert{border-left:3px solid var(--danger);background:#ff858510;padding:12px 14px;color:#ffd1d1;border-radius:6px}.single{max-width:660px;margin:10vh auto}
.transcript{grid-column:1/-1}.polling,.empty-transcript{color:var(--muted);font-size:.86rem}.turns{list-style:none;
padding:0;margin:0;display:grid;gap:12px;max-height:520px;overflow:auto}.turn{border:1px solid var(--line);border-radius:14px;
padding:16px 18px;background:#0d121b}.turn.candidate{border-left:4px solid var(--accent-2)}.turn.interviewer{border-left:4px solid var(--accent)}
.turn-meta{display:flex;align-items:center;gap:10px}.turn-meta span{color:var(--muted);font-size:.72rem;font-weight:800;
letter-spacing:.1em}.turn-meta time{margin-left:auto;color:var(--muted);font:12px ui-monospace,SFMono-Regular,Consolas,monospace}
.turn p{margin:9px 0 0;white-space:pre-wrap;overflow-wrap:anywhere}
@media(max-width:760px){.shell{padding-top:28px}.mast,.mission-header{align-items:flex-start;flex-direction:column}.mission-mark{display:none}
.layout,.mission-layout{grid-template-columns:1fr}.status-grid{grid-template-columns:1fr}.panel{padding:22px}h1{font-size:2.6rem}}
"""


def _escape(value: str) -> str:
    return html.escape(value, quote=True)
