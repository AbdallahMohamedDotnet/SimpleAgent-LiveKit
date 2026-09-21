# LiveKit Interview Agent

Local Python voice interview application under implementation. Documentation and status were
last reconciled with the repository on 21 September 2026.

The current offline implementation includes the typed two-stage dry run, SQLite evidence,
immutable snapshots, synthetic WAV recording manifests, an idempotent HR-to-technical handoff,
deterministic timing policies, a lease-safe scoring worker, recovery/retention operations, and a
read-only localhost results viewer. A localhost operator console can now create a LiveKit room,
send an explicit agent dispatch, show participant readiness, and monitor the escaped finalized
transcript. The dry run deliberately uses fakes and never contacts a provider:

```bash
.tools/bin/uv sync --group dev
.tools/bin/uv run interview dry-run --name "Candidate Name"
.tools/bin/uv run python scripts/p07_scoring_smoke.py
.tools/bin/uv run python scripts/p09_results_smoke.py
.tools/bin/uv run python scripts/p10_offline_acceptance_smoke.py
.tools/bin/uv run interview control
.tools/bin/uv run interview results
```

## Configure and start

The CLI automatically loads the ignored `.env` file from the repository root. Fill in
`OPENROUTER_API_KEY`, `ELEVEN_API_KEY`, `HR_VOICE_ID`, and `TECH_VOICE_ID`; the two voice IDs must
be different. The local LiveKit `devkey`/`secret` defaults are already present and must only be
used on localhost.

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv sync --frozen --group dev
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview config-check
```

Then follow [docs/RUNBOOK.md](docs/RUNBOOK.md) for the terminal-by-terminal LiveKit server,
ROOM Agent Server, terminal candidate, scoring worker, results viewer, cleanup, and dry-run
commands. The live path and microphone capture are verified; audible agent playback is currently
blocked because the configured ElevenLabs account returns HTTP 402 for TTS.

For a single end-user walkthrough, see [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

The P07 smoke test uses a temporary SQLite database and deterministic local assessor. It verifies
the durable scoring path without reading provider credentials or making a network request.

The project currently pins CPython 3.14.x. See `docs/compatibility.md` for the locally verified
environment and live checks that remain blocked. The microphone/STT/LLM portion of a local-room
interview is live-verified; TTS/speaker output and completion are not. Current offline gates pass
Ruff, strict mypy, and all 52 tests. The plans remain the normative specification; `PROGRESS.md`
is the single authoritative implementation-status summary.

## Current phase status

- P00: `IN_PROGRESS / BLOCKED`; microphone, STT, and opening LLM generation pass live, while
  ElevenLabs TTS returns HTTP 402 and speaker playback is unverified.
- P01: `IMPLEMENTED / PASSED`.
- P02 and P04–P08: `IN_PROGRESS / PARTIAL`; see `PROGRESS.md` for each concrete gap.
- P03: `IMPLEMENTED / PARTIAL`; the production two-session path exists, but audible handoff is
  not verified.
- P09: `IMPLEMENTED / PASSED`.
- P10: `IN_PROGRESS / BLOCKED`; offline acceptance and the microphone/STT/LLM live path pass,
  while TTS and full end-to-end acceptance remain blocked.

`interview run`, `interview join`, `interview devices`, `interview dry-run`, `interview worker`,
`interview cleanup`, `interview control`, `interview results`, `interview config-check`, and the
`interview-agent` executable are available.
The worker requires locally supplied OpenRouter configuration; its live provider call is not yet
verified. Cleanup is provider-free and runs the retryable 30-day local retention pass. Results
binds to `127.0.0.1` and defaults to port 8080. Control also binds to localhost and defaults to
port 8090. See `docs/RUNBOOK.md` for exact runnable commands and `docs/ACCEPTANCE.md` for the honest
requirement matrix.

## Use with Codex

Keep `AGENTS.md` at the repository root, then resume from the earliest ready unfinished slice in
`PROGRESS.md`. Read the core specifications and relevant `plans/Pxx` file before implementation.
Supply credentials locally when required; never paste keys into prompts or tracked files.

The requested subordinate or “slave” plans are named **implementation subplans** and numbered P00–P10. Each has dependencies, scope, implementation tasks, acceptance criteria, and a ready-to-use Codex task prompt.

## Package map

| File | Purpose |
|---|---|
| [MAIN_PLAN.md](MAIN_PLAN.md) | Scope, requirements, milestones, order, and final acceptance |
| [AGENTS.md](AGENTS.md) | Enforceable SOLID, clean-code, structure, testing, and execution instructions |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Dependency boundaries, module map, lifecycle, contracts, data, and configuration |
| [PROGRESS.md](PROGRESS.md) | Consolidated completion audit, phase status, evidence, blockers, and next steps |
| [SOURCES.md](SOURCES.md) | Source references and compatibility verification rules |
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | Configuration, startup, usage, testing, shutdown, and troubleshooting |
| `plans/P00` through `plans/P10` | Individual implementation subplans; see MAIN_PLAN links |

Readiness limitations are explicit: live microphone publication, ElevenLabs STT, and an OpenRouter
response are verified. TTS/speaker output, real-media handoff, interruption, observable recording,
and full scoring/recovery still require live tests. A console or synthetic-audio pass does not
satisfy room-based acceptance.
