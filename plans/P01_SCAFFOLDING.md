# P01 — Clean project scaffolding

Current status is tracked only in [PROGRESS.md](../PROGRESS.md).

**Read first:** [AGENTS.md](../AGENTS.md), [MAIN_PLAN.md](../MAIN_PLAN.md), [ARCHITECTURE.md](../ARCHITECTURE.md), [PROGRESS.md](../PROGRESS.md).

**Dependencies:** P00 environment findings; unresolved live checks may remain explicitly blocked.

**Requirements covered:** R01, R02, R03.

## Current state

The CPython 3.14 src-layout package, uv lockfile, centralized validated settings, redacted
secrets, composition root, typed boundaries, fakes, offline dry run, Ruff, strict mypy, pytest,
and architecture import check are implemented. LiveKit Agents and the direct ElevenLabs and
OpenAI-compatible plugins are pinned at 1.8.2. The P01 acceptance gate passed; later live voice
gates remain tracked under P00/P03/P04 rather than changing this result.

## Objective and scope

Create the minimal maintainable Python foundation with the dependency boundaries from ARCHITECTURE.md. Do not implement the entire project in an entrypoint file.

## Implementation tasks

1. Use the verified LiveKit CLI Python template workflow in the target project, preserving existing plan files. Remove unused providers, cloud deployment assumptions and unnecessary starter features.
2. Configure src layout, uv lockfile, package resources and executable entrypoints. Keep one supported Python version and document it.
3. Create only the domain models and application ports needed by the first vertical slice: InterviewRecord, StageRecord, TurnRecord, typed states, Clock, InterviewStore and StageRuntime. Add later ports when their consumers arrive.
4. Implement one settings boundary, required-key/voice validation and a secret-free `.env.example`. Keep runtime data and secrets ignored by version control.
5. Establish bootstrap as the composition root. Entry points delegate to application use cases; application code must not construct SDK clients.
6. Configure Ruff, mypy and pytest. Add a small import-boundary check forbidding domain/application imports of concrete adapters and vendor SDKs.
7. Add fake Clock/StageRuntime/Store implementations with explicit contracts. A dry run creates an interview and emits typed stage events without network access.
8. Define proposed CLI command names and help text. Mark any command not implemented yet as planned, not available.
9. Document public API types and ownership. Avoid empty directories, a generic base repository, a service locator or a large dependency-injection framework.

## Deliverables

- `pyproject.toml`, `uv.lock`, settings, entrypoints, core package modules and fake adapters.
- Offline dry-run vertical slice and quality tool configuration.
- `docs/structure.md` describing allowed imports and meaningful module responsibilities.

## Acceptance gate

- A clean dependency install and package import work with the selected interpreter.
- Missing configuration fails clearly without leaking keys.
- Offline dry run works; it does not silently call an external service.
- Lint, formatting, type checking and meaningful unit/boundary tests pass.

## Engineering review

Apply AGENTS.md to this phase. Keep business rules in domain/application code, infrastructure in adapters and construction in bootstrap. Use typed contracts and meaningful behavioral tests. Preserve cancellation, resource ownership, idempotency and accurate failure reporting. Do not introduce unused abstractions or expand the product scope.

## Handoff to the next phase

Update PROGRESS.md with implementation status, verification status, changed files, commands actually run, evidence and unresolved risks. Clearly distinguish tested behavior from assumptions. Do not mark this phase complete simply because its files exist.

## Codex task prompt

> Implement P01: Clean project scaffolding. Read the repository instructions and this subplan first. Verify prerequisites, implement the smallest complete changes satisfying its acceptance gate, and run relevant checks. Follow SOLID and the dependency rules in AGENTS.md and ARCHITECTURE.md. Preserve all fixed requirements. Record actual results and blockers in PROGRESS.md. If assigned only this phase, stop after its completion report; if assigned the whole project, continue to the next ready phase. Never present unverified live behavior as tested.
