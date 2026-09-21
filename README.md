# LiveKit Interview Agent

Local Python voice interview application under implementation. Documentation and status were
last reconciled with the repository on 21 September 2026.

The application is terminal-only: it serves no HTTP interface and has no browser UI
(see [ADR 0001](docs/adr/0001-terminal-only-operator-interface.md)). The current offline
implementation includes the typed two-stage dry run, SQLite evidence, immutable snapshots,
synthetic WAV recording manifests, an idempotent HR-to-technical handoff, deterministic timing
policies, a lease-safe scoring worker, recovery/retention operations, and read-only terminal
results commands. `interview run` creates a LiveKit room, sends an explicit agent dispatch and
joins it with terminal audio; `interview status` reports room, dispatch and participant readiness
with the finalized transcript. The dry run deliberately uses fakes and never contacts a provider:

```bash
.tools/bin/uv sync --group dev
.tools/bin/uv run interview dry-run --name "Candidate Name"
.tools/bin/uv run python scripts/p07_scoring_smoke.py
.tools/bin/uv run python scripts/p09_results_smoke.py
.tools/bin/uv run python scripts/p10_offline_acceptance_smoke.py
.tools/bin/uv run interview results list
.tools/bin/uv run interview results show --interview-id ID
```

## Run it

```bash
./run.sh
```

That opens the operator menu: start/stop the local services, run an interview with your
microphone, check live status, read results, locate recordings, list audio devices, validate
configuration, run retention cleanup, or exercise the offline dry run. Nothing else needs to be
typed. Every entry is also available as a direct command (`interview run`, `interview results
show`, ...) when you want to script it.

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
ROOM Agent Server, terminal candidate, scoring worker, results, cleanup, and dry-run
commands. Microphone capture, STT final transcripts and TTS for both voices are verified at the
provider level; an audible in-room interview has not yet been verified end to end.

For a single end-user walkthrough, see [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

The P07 smoke test uses a temporary SQLite database and deterministic local assessor. It verifies
the durable scoring path without reading provider credentials or making a network request.

The project currently pins CPython 3.14.x. See `docs/compatibility.md` for the locally verified
environment and live checks that remain blocked. The microphone/STT/LLM portion of a local-room
interview is live-verified; TTS/speaker output and completion are not. Current offline gates pass
Ruff, strict mypy, and the full pytest suite. The plans remain the normative specification;
`PROGRESS.md` is the single authoritative implementation-status summary.

## Current phase status

- P00: `IN_PROGRESS / PARTIAL`; microphone, STT, opening LLM generation, and TTS for both voices
  pass live at the provider level; in-room speaker playback is unverified.
- P01: `IMPLEMENTED / PASSED`.
- P02 and P04–P08: `IN_PROGRESS / PARTIAL`; see `PROGRESS.md` for each concrete gap.
- P03: `IMPLEMENTED / PARTIAL`; the production two-session path exists, but audible handoff is
  not verified.
- P09: `IMPLEMENTED / PASSED`.
- P10: `IN_PROGRESS / BLOCKED`; offline acceptance and the microphone/STT/LLM live path pass,
  while TTS and full end-to-end acceptance remain blocked.

`interview run`, `interview join`, `interview status`, `interview devices`, `interview dry-run`,
`interview worker`, `interview cleanup`, `interview results list|show|recording`,
`interview config-check`, and the `interview-agent` executable are available.
The worker requires locally supplied OpenRouter configuration; its live provider call is not yet
verified. Cleanup is provider-free and runs the retryable 30-day local retention pass. The results
commands are short-lived readers: they open no socket, escape untrusted text before printing it,
and resolve recordings only to validated paths under the owned recordings root. Add `--json` to
`status` or any `results` subcommand for scripting. See `docs/RUNBOOK.md` for exact runnable
commands and `docs/ACCEPTANCE.md` for the honest requirement matrix.

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
| [docs/adr/](docs/adr/) | Architecture decision records, including the terminal-only interface |
| `plans/P00` through `plans/P10` | Individual implementation subplans; see MAIN_PLAN links |

Readiness limitations are explicit: live microphone publication, ElevenLabs STT, and an OpenRouter
response are verified. TTS/speaker output, real-media handoff, interruption, observable recording,
and full scoring/recovery still require live tests. A synthetic-audio pass does not
satisfy room-based acceptance.
