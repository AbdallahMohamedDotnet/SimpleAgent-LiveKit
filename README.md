# LiveKit Interview Agent

Local Python voice interview application under implementation. Documentation and status were
last reconciled with the repository on 21 September 2026.

The current offline implementation includes the typed two-stage dry run, SQLite evidence,
immutable snapshots, synthetic WAV recording manifests, an idempotent HR-to-technical handoff,
deterministic timing policies, a lease-safe scoring worker, recovery/retention operations, and a
read-only localhost results viewer. The dry run deliberately uses fakes and never contacts a
provider:

```bash
.tools/bin/uv sync --group dev
.tools/bin/uv run interview dry-run --name "Candidate Name"
.tools/bin/uv run python scripts/p07_scoring_smoke.py
.tools/bin/uv run python scripts/p09_results_smoke.py
.tools/bin/uv run python scripts/p10_offline_acceptance_smoke.py
.tools/bin/uv run interview results
```

The P07 smoke test uses a temporary SQLite database and deterministic local assessor. It verifies
the durable scoring path without reading provider credentials or making a network request.

The project currently pins CPython 3.14.x. See `docs/compatibility.md` for the locally verified
environment and live checks that remain blocked. A local-room voice interview has not yet been
verified. Current offline gates pass Ruff, strict mypy, and 40 tests. The plans remain the
normative specification; implementation and verification status are tracked separately in
`PROGRESS.md` and summarized at the top of every phase plan.

## Current phase status

- P00: `IN_PROGRESS / BLOCKED` on physical audio and provider credentials.
- P01: `IMPLEMENTED / PASSED`.
- P02–P08: `IN_PROGRESS / PARTIAL`; implemented offline slices pass while live or later slices
  remain.
- P09: `IMPLEMENTED / PASSED`.
- P10: `IN_PROGRESS / BLOCKED`; the offline acceptance smoke and runbook pass, while production
  room/audio/provider acceptance remains blocked.

`interview dry-run`, `interview worker`, `interview cleanup`, and `interview results` are available.
The worker requires locally supplied OpenRouter configuration; its live provider call is not yet
verified. Cleanup is provider-free and runs the retryable 30-day local retention pass. Results
binds to `127.0.0.1` and defaults to port 8080. The production `run` and `status` commands remain
planned. See `docs/RUNBOOK.md` for exact runnable commands and `docs/ACCEPTANCE.md` for the honest
requirement matrix.

## Use with Codex

1. Keep `AGENTS.md` at the repository root so Codex can discover the project instructions.
2. Open this directory in Codex on the Ubuntu machine.
3. Use `CODEX_START.md` to resume from the earliest ready unfinished slice in `PROGRESS.md`.
4. Codex reads the core specifications and relevant `plans/Pxx` file before implementation.
5. Supply credentials locally when required. Never paste keys into prompts or tracked files.

The requested subordinate or “slave” plans are named **implementation subplans** and numbered P00–P10. Each has dependencies, scope, implementation tasks, acceptance criteria, and a ready-to-use Codex task prompt.

## Package map

| File | Purpose |
|---|---|
| [MAIN_PLAN.md](MAIN_PLAN.md) | Scope, requirements, milestones, order, and final acceptance |
| [AGENTS.md](AGENTS.md) | Enforceable SOLID, clean-code, structure, testing, and execution instructions |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Dependency boundaries, module map, lifecycle, contracts, data, and configuration |
| [CODEX_START.md](CODEX_START.md) | Copy-and-paste implementation prompt |
| [PROGRESS.md](PROGRESS.md) | Honest phase status and evidence ledger |
| [SOURCES.md](SOURCES.md) | Source references and compatibility verification rules |
| `plans/P00` through `plans/P10` | Individual implementation subplans; see MAIN_PLAN links |

Readiness limitations are explicit: installed SDK/CLI versions and media-disabled session cleanup
are verified; model access, terminal audio in a real room, real-media handoff, interruption, and
observable recording still require live tests. A console or synthetic-audio pass does not satisfy
room-based acceptance.
