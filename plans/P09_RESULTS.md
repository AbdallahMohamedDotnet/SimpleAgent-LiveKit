# P09 — Minimal read-only HTML results

Current status is tracked only in [PROGRESS.md](../PROGRESS.md).

**Read first:** [AGENTS.md](../AGENTS.md), [MAIN_PLAN.md](../MAIN_PLAN.md), [ARCHITECTURE.md](../ARCHITECTURE.md), [PROGRESS.md](../PROGRESS.md).

**Dependencies:** P07–P08.

**Requirements covered:** R14–R17.

## Current state

The read-only result DTO/port, expiry-safe SQLite projection, escaped server-rendered HTML,
localhost server, list/detail/audio routes, protected owned-root media reader, CLI command, and
rendering/security tests are implemented. HR and Technical remain separate, pending/failed/null
states are explicit, evidence links target finalized turns, and recording failures/gaps are shown.
The offline HTTP smoke and the complete quality suite pass; no provider request was required.

## Objective and scope

Provide a simple local view of stored results without building a candidate interview frontend or a complex web application.

## Implementation tasks

1. Add a read-only ResultsReader and query DTOs; keep SQL in its SQLite adapter and presentation formatting in the web adapter.
2. Bind a small server to 127.0.0.1. Render server-side HTML; use simple refresh or bounded polling for pending assessments.
3. List candidate name, time, conversation status, HR score/coverage, technical score/coverage and assessment status. Display pending/null accurately rather than zero.
4. Add a detail page with competency scores, rationale, evidence turn links, separate stage transcripts, hints, observed difficulty boundaries and recording playback/gaps.
5. Display the two stage results separately and do not add a combined ranking or automatic hiring recommendation.
6. Escape candidate names, transcripts and LLM text. Serve audio through authorized local record IDs resolved under the owned root, never a user-supplied raw path.
7. Filter expired records/media even when scheduled cleanup is pending. Do not expose the SQLite database, environment files or arbitrary files.
8. Keep the page read-only: no interview creation, score editing, CV upload or microphone flow.
9. Test rendering with malicious-looking HTML strings, duplicate names, pending/failed/incomplete records, missing media and expired IDs.

## Deliverables

- Local results entrypoint, escaped templates and read-only query adapter.
- List/detail/audio routes with consistent pending/failed/null display.
- Rendering and media-path security tests.

## Acceptance gate

- HR results may appear while Technical is still active; later technical results update correctly.
- Evidence/transcript/audio links resolve or show an explicit unavailable state.
- Untrusted text is rendered as text, not executable markup.
- Expired data and arbitrary paths cannot be retrieved. No write actions are exposed.

## Engineering review

Apply AGENTS.md to this phase. Keep business rules in domain/application code, infrastructure in adapters and construction in bootstrap. Use typed contracts and meaningful behavioral tests. Preserve cancellation, resource ownership, idempotency and accurate failure reporting. Do not introduce unused abstractions or expand the product scope.

## Handoff to the next phase

P09 is complete. P10 can now exercise the retained local viewer as part of the end-to-end runbook
and acceptance workflow. Live provider/device evidence remains a project-level blocker recorded
under the earlier phases; it does not change the verified P09 read-only boundary.

## Codex task prompt

> Implement P09: Minimal read-only HTML results. Read the repository instructions and this subplan first. Verify prerequisites, implement the smallest complete changes satisfying its acceptance gate, and run relevant checks. Follow SOLID and the dependency rules in AGENTS.md and ARCHITECTURE.md. Preserve all fixed requirements. Record actual results and blockers in PROGRESS.md. If assigned only this phase, stop after its completion report; if assigned the whole project, continue to the next ready phase. Never present unverified live behavior as tested.
