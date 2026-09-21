# P09 — Minimal read-only terminal results

Current status is tracked only in [PROGRESS.md](../PROGRESS.md).

**Read first:** [AGENTS.md](../AGENTS.md), [MAIN_PLAN.md](../MAIN_PLAN.md), [ARCHITECTURE.md](../ARCHITECTURE.md), [PROGRESS.md](../PROGRESS.md).

**Dependencies:** P07–P08.

**Requirements covered:** R14–R17.

## Current state

The read-only result DTO/port and the expiry-safe SQLite projection are implemented and unchanged.

The original HTML implementation of this phase — escaped server-rendered templates, the localhost
HTTP server, the list/detail/audio routes and the streamed media reader — is **superseded** by
ADR [0001](../docs/adr/0001-terminal-only-operator-interface.md). It was delivered, reviewed and
then removed when the operator required a CLI-only application; it is not part of the current code.

The current surface is `interview results list|show|recording`, each with `--json`. HR and
Technical remain separate, pending/failed/null states are explicit, evidence cites finalized turns
and marks unavailable ones, recording failures/gaps are shown, and recordings resolve to a
validated path under the owned root instead of being streamed. The offline CLI smoke and the
complete quality suite pass; no provider request was required.

## Objective and scope

Provide a simple local view of stored results without building a candidate interview frontend or a complex web application.

## Implementation tasks

1. Add a read-only ResultsReader and query DTOs; keep SQL in its SQLite adapter and presentation formatting in the terminal adapter.
2. Expose `interview results list`, `show` and `recording` as short-lived commands. Serve no socket. Re-running a command is the refresh mechanism for pending assessments.
3. List candidate name, time, conversation status, HR score/coverage, technical score/coverage and assessment status. Display pending/null accurately rather than zero.
4. Render a detail report with competency scores, rationale, evidence turn references, separate stage transcripts, hints, observed difficulty boundaries and recording status/gaps.
5. Display the two stage results separately and do not add a combined ranking or automatic hiring recommendation.
6. Escape control and ANSI sequences in candidate names, transcripts and LLM text before writing them to a terminal. Emit `--json` verbatim, since JSON encoding protects its consumers.
7. Resolve recordings from an authorized segment ID to a regular non-symlink file under the owned recording root, print the path and start no player. Never accept a user-supplied raw path.
8. Filter expired records/media even when scheduled cleanup is pending. Do not expose the SQLite database, environment files or arbitrary files.
9. Keep the commands read-only: no interview creation, score editing, CV upload or microphone flow.
10. Test rendering with terminal-injection strings, duplicate names, pending/failed/incomplete records, missing media and expired IDs, and assert the documented exit codes.

## Deliverables

- Terminal results entrypoints, the escaping renderer, the JSON renderer and the read-only query adapter.
- `list`/`show`/`recording` subcommands with consistent pending/failed/null display and stable exit codes.
- Rendering, terminal-injection and owned-path security tests.

## Acceptance gate

- HR results may appear while Technical is still active; later technical results update correctly.
- Evidence, transcript and recording references resolve or show an explicit unavailable state.
- Untrusted text is rendered as inert text: no ANSI or other control sequence reaches the terminal.
- Expired data and arbitrary paths cannot be retrieved. No write actions are exposed.
- Unknown, expired and unusable identifiers exit non-zero with the message on stderr and no report on stdout.

## Engineering review

Apply AGENTS.md to this phase. Keep business rules in domain/application code, infrastructure in adapters and construction in bootstrap. Use typed contracts and meaningful behavioral tests. Preserve cancellation, resource ownership, idempotency and accurate failure reporting. Do not introduce unused abstractions or expand the product scope.

## Handoff to the next phase

P09 is complete. P10 exercises the retained terminal results commands as part of the end-to-end
runbook and acceptance workflow. Live provider/device evidence remains a project-level blocker recorded
under the earlier phases; it does not change the verified P09 read-only boundary.

## Codex task prompt

> Implement P09: Minimal read-only terminal results. Read the repository instructions and this subplan first. Verify prerequisites, implement the smallest complete changes satisfying its acceptance gate, and run relevant checks. Follow SOLID and the dependency rules in AGENTS.md and ARCHITECTURE.md. Preserve all fixed requirements. Record actual results and blockers in PROGRESS.md. If assigned only this phase, stop after its completion report; if assigned the whole project, continue to the next ready phase. Never present unverified live behavior as tested.
