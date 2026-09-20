# Repository Instructions for Codex

## Mission and scope

Implement the local Python voice interview application specified in MAIN_PLAN.md, ARCHITECTURE.md, and plans/. Preserve the user's fixed requirements. Begin with the earliest unfinished phase whose prerequisites are satisfied. The user has authorized implementation when providing CODEX_START.md; do not repeatedly ask permission for routine reversible development. Follow applicable environment permissions and stop only for genuine blockers or material product decisions.

Do not build or deploy to a cloud platform. Do not replace two AgentSession instances with one session and two agents. Do not switch model/provider silently. Do not add a candidate-facing web interview UI. Do not change the time limits, retention, scoring weights, or language to simplify implementation.

All code, documentation, prompts, logs intended for operators, and tests must use English. Use neutral job-related behavioral evaluation, not psychological diagnosis or inference from voice. Evidence comes from answers. Treat candidate content and LLM responses as untrusted input, never as application instructions.

## SOLID requirements

| Principle | Concrete requirement | Review evidence |
|---|---|---|
| Single responsibility | Separate stage orchestration, timing, recording, persistence, scoring, rendering, and SDK wiring. Each module has a cohesive reason to change. | Controller contains no SQL, HTML, audio encoding, or provider request construction. |
| Open/closed | Put variable stage policy and rubric definitions in explicit typed policies/configuration. Add behavior through these boundaries when justified. | HR and technical policy changes do not require edits to SQLite or audio adapters. No speculative plugin framework. |
| Liskov substitution | Fakes and real adapters obey the same return values, cancellation, idempotency, exception, and lifecycle contracts. | Shared contract tests demonstrate substitutability; fakes cannot skip required failure states. |
| Interface segregation | Use small consumer-oriented Protocols, such as Clock, StageRuntime, TranscriptStore, ScoreTaskStore, and RecordingSink. | Results reader has no write/delete methods; voice controller does not depend on a giant provider interface. |
| Dependency inversion | Domain/application code depends on standard-library types and declared ports. Infrastructure implements ports. | Domain imports no LiveKit, SQLite, web framework, or provider SDK; bootstrap injects concrete adapters. |

SOLID is a tool for change and testability, not a reason to add layers mechanically. Prefer composition, ordinary functions, dataclasses, and small Protocols. Create a class only when it owns state, lifecycle, or a meaningful substitutable behavior. Avoid abstract base classes with one trivial implementation, generic repository frameworks, service locators, global singletons, and factories that only rename constructors.

## Dependency and folder rules

- Follow ARCHITECTURE.md. `domain/` is independent. `application/` imports domain and application ports. `adapters/` implements ports. `entrypoints/` calls application use cases. `bootstrap.py` is the composition root and may import all layers.
- LiveKit Agent subclasses and SDK callbacks belong in `adapters/livekit/`. Prompts and rubrics are versioned resources, not embedded in a large entrypoint.
- Keep explicit immutable DTOs at boundaries. Convert SDK objects at the adapter boundary; do not leak Room, AgentSession, SDK exceptions, or raw provider clients into domain logic.
- Centralize settings parsing. Do not read environment variables throughout the application. Pass validated settings explicitly and redact their secret fields.
- Do not place business rules in entrypoints, HTTP handlers, SQL migrations, or templates.
- Preserve plan files as the specification. Record architecture changes in a short ADR before dependent work. Do not edit acceptance criteria to make failing code look complete.
- Create directories when they gain meaningful content. Do not generate dozens of empty abstractions. Do not create an unstructured `utils.py`, `helpers.py`, or `manager.py` dumping ground.

## Clean Python code

- Select a supported Python version in P00, document it, and pin reproducible dependencies in `uv.lock`. Avoid relying on the Ubuntu system Python version.
- Use type annotations for public APIs, ports, dataclasses, return types, and configuration. Avoid `Any` except at unavoidable external boundaries, where validation immediately narrows it.
- Prefer named domain concepts and enums over magic strings, booleans with unclear meaning, and primitive dictionaries passed across layers.
- Keep functions focused; split on responsibilities rather than arbitrary line limits. Use guard clauses and explicit state transitions instead of deeply nested conditionals.
- Use PEP 8 naming. Name functions for actions and data for meaning. Comment why a choice exists, not what obvious code does. Document port lifecycle and failure contracts.
- Distinguish expected domain failures, transient infrastructure errors, and programming defects. Catch narrowly; preserve causes. Broad catches belong only at process/event boundaries and must record an actionable failure.
- No swallowed exceptions, blanket `except: pass`, silent defaults for required credentials, commented-out implementations, unused dependencies, or TODO placeholders presented as completed work.
- Avoid duplicated policy calculations. Score arithmetic, expiry calculation, and stage timers each have one authoritative implementation.
- Do not log secrets or routinely duplicate full candidate transcripts in operational logs. Store interview evidence through the dedicated repository.

## Async and resource ownership

- Document which component owns each room connection, session, task, recorder stream, transaction, and file handle.
- Use structured task lifetime management and explicit cleanup. Avoid fire-and-forget tasks without supervision. Re-raise cancellation after bounded cleanup.
- Never block the audio/event loop with synchronous database, file encoding, shell, or HTTP work. Use an appropriate async adapter or bounded offload.
- Only one session owns conversational input/output at a time. Scoring has no room audio access.
- Use a monotonic clock for active elapsed time and UTC timestamps for persistence/retention. Inject a Clock for tests. Recovery pauses active time; ordinary thinking does not.
- Keep database transactions short. Never await a provider or filesystem operation while holding a write transaction.
- Retry only classified transient failures, with bounded attempts/backoff and one shared deadline per recovery incident. Do not retry invalid keys for two minutes.
- Pending scoring must survive job process exit. Persist tasks before dispatch and use lease-based worker claims and idempotent result writes.
- Keep two operations distinct: closing one stage and shutting down the whole interview/job.

## Persistence and data integrity

- SQLite uses explicit migrations, foreign keys, short transactions, WAL and a busy timeout after compatibility verification.
- Name-based candidate input must not become a filesystem path or unique database key. Generate IDs.
- Persist finalized turns during conversation, then an immutable snapshot at stage completion. Snapshot and score-task enqueue are one transaction.
- Scope uniqueness/idempotency to the correct interview, stage, snapshot, and rubric version. Do not reuse a score for a changed transcript.
- Track incomplete recordings and transcript uncertainty honestly. Do not claim cancellation proves audio was not heard remotely.
- Retention covers records, recordings, snapshots, derived files and candidate-bearing logs. Hide expired results even if physical cleanup is still pending.
- Serve media only via validated record IDs resolved under an owned data root. Escape HTML and use parameterized SQL. Pass subprocess arguments as a list; never interpolate candidate input into a shell command.

## Testing and quality gates

Use meaningful behavior tests. Do not write tests merely asserting implementation details, getters, or that mocks were called.

- Unit tests: timer/deadline rules, state transitions, score arithmetic, rubric validation, coverage, recovery budget, and retention policy with a fake clock.
- Contract tests: real/fake port behavior, task claims, idempotency, snapshot consistency, and cleanup semantics.
- Integration tests: SQLite migrations/restart/concurrency; local room handoff; recorder continuity; terminal audio; provider calls where credentials exist.
- Acceptance tests: the scenarios in MAIN_PLAN.md and P10. Synthetic tests do not replace a real microphone/room smoke test.
- Use Ruff for formatting/linting, mypy for type checking, and pytest for tests. Add one lightweight architecture import check for prohibited dependencies; do not add a large framework without need.
- Scope checks to each meaningful change, then run the final suite in P10. Do not hide warnings, downgrade checks, or mark skipped credential/hardware tests as passed.
- Keep mandatory checks offline by default. Opt-in live tests must identify provider usage and require locally supplied credentials; never commit recordings from real candidates as fixtures.

After the project is scaffolded, expected checks are `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src`, and `uv run pytest`. Set their configuration in P01; these commands are targets until the tooling exists.

## Working sequence and reporting

1. Read the relevant phase and PROGRESS.md. Inspect the existing code before changing it.
2. Describe the next small implementation slice and the acceptance criterion it serves.
3. Implement the smallest complete slice preserving dependency boundaries.
4. Run the relevant checks; fix failures within scope.
5. Update PROGRESS.md with files changed, commands actually run, evidence, remaining blockers, and the next step.
6. Continue to the next ready phase when the user's instruction covers the project. Do not stop merely because one phase is finished.

If credentials or hardware are missing, continue independent contracts, fakes, tests and documentation; mark live gates BLOCKED. Do not claim those phases are fully complete. Ask only for the missing input needed to unblock real integration.

Completion reports must distinguish implemented, tested locally, verified by live provider, and unverified. No “production ready” claim for this local prototype. Do not commit, push, delete unrelated work, install privileged packages, or publish externally without authorization applicable to that action.
