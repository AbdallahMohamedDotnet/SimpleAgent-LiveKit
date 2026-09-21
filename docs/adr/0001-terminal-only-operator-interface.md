# ADR 0001 — Terminal-only operator interface

- Status: accepted
- Date: 2026-09-21
- Supersedes: the HTML results viewer and HTML operator console delivered in P09 and P03.

## Context

R17 originally required a localhost HTML results viewer, and P03 added a localhost HTML operator
console for room creation and agent dispatch. Both were served by `http.server` adapters under
`src/interview_app/adapters/web/`, reachable only from `127.0.0.1` on `RESULTS_PORT` and
`CONTROL_PORT`.

The operator asked for a CLI-only workflow: the application must be driven entirely from the
`interview` and `interview-agent` commands, with no browser and no application HTTP server. The
two surfaces were the only reason the project bound a socket, escaped HTML, and shipped
port configuration.

## Decision

The application has no HTTP surface. Operators create, join, monitor and read interviews from the
terminal:

- `interview run` / `interview join` keep the existing Python terminal RTC client. The installed
  `lk room join` command does not provide the bidirectional microphone/speaker path this
  application needs, so the terminal client is not replaced by the LiveKit CLI.
- `interview status` replaces the console's room, dispatch and participant view.
- `interview results list|show|recording` replaces the HTML viewer, with `--json` for scripting.

The read-only `ResultsReader` port, its immutable DTOs and the SQLite adapter are unchanged; only
the presentation adapter changed. Two sequential `AgentSession` instances, scoring, timing,
retention and the configured providers are unchanged.

## Consequences

- `adapters/web/`, the `control` command, `build_control_application`, `build_results_application`,
  `ControlSettings`, `ResultsSettings.host/port`, `CONTROL_HOST`, `CONTROL_PORT`, `RESULTS_HOST`
  and `RESULTS_PORT` are removed. `ControlSettings` becomes `LaunchSettings`, which carries the
  LiveKit binding with no network-listener fields.
- HTML escaping is replaced by terminal escaping: `adapters/terminal/sanitize.py` neutralizes ANSI
  and other control characters in every untrusted value rendered for a human. `--json` output is
  emitted verbatim because JSON encoding already protects its consumers.
- Recordings are no longer streamed. `interview results recording` resolves a validated segment ID
  to a regular, non-symlink file under the owned recordings root and prints the path; the operator
  chooses the player. No external process is launched with candidate-derived input.
- `scripts/run_local.sh` starts only the LiveKit dev server, ROOM Agent Server, retention cleanup
  and scoring worker. It performs no port checks for application services and prints no URLs.
- The browser-specific gates (localhost binding, HTML escaping, CSRF, GET/HEAD-only routing) no
  longer exist as acceptance criteria. They are replaced by terminal-injection, exit-code and
  owned-path gates. P09's HTML implementation is superseded, not retroactively removed from the
  project history.
