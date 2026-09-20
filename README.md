# LiveKit Interview Agent

Local Python voice interview application under implementation. Documentation and status were
last reconciled with the repository on 20 September 2026.

The current offline implementation includes the typed two-stage dry run, SQLite evidence and
lease persistence, immutable snapshots, synthetic WAV recording manifests, an idempotent HR to
technical handoff controller, deterministic timing/idle policies, and pinned provider factories.
The dry run deliberately uses fakes and never contacts a provider:

```bash
.tools/bin/uv sync --group dev
.tools/bin/uv run interview dry-run --name "Candidate Name"
```

The project currently pins CPython 3.14.x. See `docs/compatibility.md` for the locally verified
environment and live checks that remain blocked. A local-room voice interview has not yet been
verified. Current offline gates pass Ruff, strict mypy, and 15 tests. The plans remain the
normative specification; implementation and verification status are tracked separately in
`PROGRESS.md` and summarized at the top of every phase plan.

## Current phase status

- P00: `IN_PROGRESS / BLOCKED` on physical audio and provider credentials.
- P01: `IMPLEMENTED / PASSED`.
- P02–P04: `IN_PROGRESS / PARTIAL`; offline slices pass, live adapters/gates remain.
- P05–P10: `NOT_STARTED / NOT_RUN`.

Only `interview dry-run` is currently available. The production `run`, `worker`, `results`,
`cleanup`, and `status` commands remain planned.

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
