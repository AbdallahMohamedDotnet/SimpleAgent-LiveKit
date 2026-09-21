# Project completion audit

Last reconciled: 21 September 2026.

This is the single authoritative implementation-status summary for `MAIN_PLAN.md`,
`ARCHITECTURE.md`, and `plans/P00` through `plans/P10`. The plan files remain the normative
specification. Detailed operating instructions and reproducible evidence remain in
`docs/RUNBOOK.md`, `docs/ACCEPTANCE.md`, and `docs/compatibility.md`.

## Verdict

The project is **not complete**. The local application, production ROOM Agent Server, terminal
RTC candidate, persistence, scoring worker, retention workflow, terminal launch/status commands,
and terminal results commands are implemented far enough for the complete offline suite to pass.
The application is now terminal-only: both localhost HTML surfaces were removed under ADR
[0001](docs/adr/0001-terminal-only-operator-interface.md), and no HTTP server remains. A real microphone
track reached ElevenLabs STT, and OpenRouter generated the opening HR question. On 21 September
2026 the two live voice faults were diagnosed and fixed: STT produced only partial transcripts
because nothing committed them (server-side VAD is now enabled), and the HTTP 402 was not a
billing limit — the configured HR voice was a library voice that free accounts cannot use through
the API (HR now uses the default voice Sarah). Both are verified at the provider level; an audible
in-room interview, the two-stage handoff, and full end-to-end acceptance are still unverified.

No phase is marked complete merely because its files exist. Implementation and verification are
reported separately.

## Phase audit

| Phase | Implementation | Verification | Completed evidence | Remaining work |
|---|---|---|---|---|
| P00 compatibility | IN_PROGRESS | BLOCKED | Ubuntu 26.04.1 x86_64, CPython 3.14.4, uv 0.12.17, LiveKit CLI 2.18.2, LiveKit Server 1.13.7, local room/signaling, microphone publication, ElevenLabs STT, and OpenRouter generation were exercised. | Enable ElevenLabs billing/credits and verify TTS, speaker output, both voices, interruption, and real-media drain/capture. |
| P01 scaffolding | IMPLEMENTED | PASSED | Packaged source layout, pinned lockfile, typed settings, boundaries, CLI, Ruff, strict mypy, pytest, and architecture checks pass. | None. |
| P02 persistence/recording | IN_PROGRESS | PARTIAL | SQLite migrations, WAL/foreign keys/busy timeout, idempotent turns/events, immutable snapshots, atomic score enqueue, leases, WAV segments, manifests, checksums, gaps, and restart behavior pass. | Connect the recorder to observable candidate and agent room media; verify alignment and incomplete-media behavior with real audio. |
| P03 lifecycle/handoff | IMPLEMENTED | PARTIAL | A real ROOM dispatch is claimed; durable identity is reused; two distinct `AgentSession` instances run sequentially; HR closes and enqueues scoring before Technical starts; final Technical scoring is enqueued. | Verify audible same-room handoff, final speech drain, and zero overlapping I/O ownership with both live voices. |
| P04 voice/timing | IN_PROGRESS | PARTIAL | Fixed provider construction, live STT/opening LLM response, 300-second policies, answer completion, overrun, five-second idle policy, thinking hold, transcript persistence, and cleanup barriers pass applicable tests. | Verify TTS/playout, live deadline crossing, VAD/barge-in, idle reminder, thinking extension, and recovery timer behavior. |
| P05 HR interview | IN_PROGRESS | PARTIAL | Versioned neutral HR instructions/rubric and evidence/injection boundaries pass; one opening HR question was generated live. | Complete a live behavioral stage and add/verify competency-turn tagging, completion control, and synthetic strong/weak/vague conversations. |
| P06 technical interview | IN_PROGRESS | PARTIAL | Versioned rubric, attributed HR context, Junior-first progression, clarification, and one-hint policy pass offline. | Persist case/difficulty/hint decisions and verify live adaptive questioning, observed boundaries, and provider behavior. |
| P07 scoring | IN_PROGRESS | PARTIAL | Durable worker, leases, retries/final failures, strict JSON/evidence validation, null-aware independent averages, idempotent writes, and results persistence pass offline. | Run live Sonnet 5 scoring/calibration, including strong, weak, assisted, incomplete, and deliberately slow HR scoring while Technical continues. |
| P08 recovery/retention | IN_PROGRESS | PARTIAL | Fixed 120-second recovery budget, checkpoints/reconciliation contracts (reconciliation now runs at agent-server startup; early job exits close their interview), exact 30-day expiry, safe retryable artifact deletion, worker races, cleanup CLI, and daily user timer pass locally. | Wire checkpoints/recovery into the production live controller and verify real reconnect, track rebind, recorder segmentation, and timeout behavior. |
| P09 results | IMPLEMENTED | PASSED | Expiry-safe read DTOs, terminal-escaped rendering, stable `--json`, separate HR/Technical results, evidence turn references, pending/null/failure display, ID-authorized recording paths, and documented exit codes pass CLI/security tests. The superseded HTML viewer was removed under ADR 0001. | None within P09. |
| P10 acceptance/runbook | IN_PROGRESS | BLOCKED | Runbook, user guide, terminal launch/status/results commands, offline acceptance smoke, architecture gate (including a no-HTTP-surface check), and quality suite pass. | Complete all blocked live scenarios after TTS is available, then record full same-room handoff, scoring concurrency, recovery, recording, and final results evidence. |

Only P01 and P09 are fully implemented and verified. P03 is implemented but not fully live-verified.

## Requirement audit

| Requirement | Status | Summary |
|---|---|---|
| R01 | PASSED | Required Ubuntu/Python/toolchain versions are selected, documented, and locked. |
| R02 | PARTIAL | Local-only LiveKit server, CLI, rooms, dispatch, RTC participant, and agent job work; full audio remains incomplete. |
| R03 | PARTIAL | Name-only launch, generated IDs, and one-active-interview enforcement work; complete live interview is blocked. |
| R04 | PARTIAL | One room and two distinct sessions are implemented; audible media handoff is unverified. |
| R05 | PARTIAL | HR prompts/rubric satisfy the content policy; a complete live HR stage is unverified. |
| R06 | PARTIAL | Technical prompts/rubric cover the required domains; live adaptive stage is unverified. |
| R07 | PARTIAL | Dynamic prompt policy, Junior-first progression, and hint limits exist; durable live case/hint evidence is incomplete. |
| R08 | PARTIAL | Deadline policy passes deterministic tests; live speech-boundary behavior is unverified. |
| R09 | PARTIAL | English-only and English-neutral scoring rules are enforced in configuration/resources; full provider behavior is unverified. |
| R10 | PARTIAL | Idle/thinking/interruption policies exist; live VAD, barge-in, and reminders are unverified. |
| R11 | PARTIAL | ElevenLabs STT now commits final transcripts and both distinct voices stream audio (provider-level live probes, 21 Sep 2026). In-room speaker playback is unverified. |
| R12 | PARTIAL | OpenRouter Sonnet 5 generated the opening question live; live scoring and all-task verification remain. |
| R13 | PARTIAL | HR snapshot/task enqueue precedes Technical and scoring owns no room I/O; slow live scoring concurrency is unverified. |
| R14 | PARTIAL | Evidence validation, 1–5/null rules, coverage, and independent stage scores pass offline; live calibration remains. |
| R15 | PARTIAL | Records and synthetic WAV artifacts persist; real room recording and technical case/hint evidence are incomplete. |
| R16 | PASSED | Exact 30-day hiding/deletion, retry behavior, worker races, CLI, and scheduled local cleanup pass. |
| R17 | PASSED | The read-only `interview results` commands pass functionality, terminal-injection, owned-path and exit-code checks. No HTTP interface or web UI exists (ADR 0001). |
| R18 | PARTIAL | Recovery policy and persistence pass offline; production reconnect/checkpoint/media recovery is incomplete. |
| R19 | PASSED | No in-agent consent step is present, as required. |

Detailed scenario evidence is retained in `docs/ACCEPTANCE.md`.

## Implemented operator workflow

The repository exposes one interactive entry point and the individual commands it calls:

```text
./run.sh                      # main.py -> interactive operator menu
interview config-check
interview dry-run --name "Candidate Name"
interview run --name "Candidate Name" [--input-device DEVICE] [--output-device DEVICE]
interview join --interview-id ID [--input-device DEVICE] [--output-device DEVICE]
interview devices
interview worker [--once]
interview status --interview-id ID [--json]
interview cleanup
interview results list [--json]
interview results show --interview-id ID [--json]
interview results recording --segment-id ID [--json]
interview-agent dev --no-reload
```

`./run.sh` opens the menu; it prompts and delegates, holding no policy of its own, and stops any
background services it started when the operator quits. Every surface is a terminal command; the
application opens no listening socket. Candidate
microphone and speaker I/O remain in `interview run`/`interview join`. The read-only commands
escape untrusted text before printing it, emit `--json` verbatim for decoders, resolve recordings
only to validated paths under the owned recordings root, and exit `3` for unknown, expired or
unavailable identifiers. SQLite contains interview evidence and local files contain recording
artifacts. The scoring worker has no room-audio access.

## Latest verification

The following checks were executed against the current working tree on 21 September 2026:

```text
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run --frozen ruff format --check .
  PASS: 128 files already formatted
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run --frozen ruff check .
  PASS
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run --frozen mypy src
  PASS: 71 source files
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run --frozen pytest
  PASS: 68 tests in 1.87 seconds
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run --frozen python scripts/p09_results_smoke.py
  PASS: list/show/json/recording exit 0; unknown segment exits 3; injected ANSI escaped
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run --frozen python scripts/p10_offline_acceptance_smoke.py
  PASS: offline_only; provider_request_made=false; live_audio_verified=false
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run --frozen interview config-check
  PASS: configuration=valid; secrets=redacted
bash -n run.sh scripts/run_local.sh
  PASS
printf '1\n2\n0\n' | ./run.sh
  PASS: services started (livekit reachable), stopped on request, no leftover processes
```

The CLI-only migration removed `src/interview_app/adapters/web/`,
`src/interview_app/entrypoints/control.py`, the `interview control` command, the HTTP-serving
`interview results` command, `build_control_application`, `build_results_application`,
`ControlSettings`, and the `CONTROL_HOST`/`CONTROL_PORT`/`RESULTS_HOST`/`RESULTS_PORT` settings.
It added `src/interview_app/adapters/terminal/`, `interview status`, the `results`
`list`/`show`/`recording` subcommands, `LaunchSettings`, `LocalRecordingLocator`, and CLI
behavior, terminal-injection and no-HTTP-surface tests. The `ResultsReader` port, its DTOs, the
SQLite projection, the two sequential `AgentSession` design, scoring, timing, retention and the
configured providers are unchanged. An existing local `.env` may still contain the removed
`RESULTS_*`/`CONTROL_*` keys; they are ignored and can be deleted.

The restricted sandbox stalled at the known SQLite integration point. The pytest suite and
offline acceptance smoke were therefore rerun with ordinary host permissions and passed. No new
provider request was made during this audit.

Previously verified live evidence:

- A project-local PortAudio runtime enumerated PipeWire/ALSA devices.
- A terminal candidate published an unmuted microphone track in room `RM_vxgMgPepn2Xo`.
- ElevenLabs realtime STT produced partial and final candidate text.
- OpenRouter generated and persisted the opening HR question.
- A direct ElevenLabs TTS probe returned non-retryable HTTP 402 `Payment Required` and produced no
  audio frames. Diagnosed on 21 September 2026: the response code was `paid_plan_required` for the
  HR voice `21m00Tcm4TlvDq8ikWAM` (a library voice); the technical voice returned audio.
- 21 September 2026: after the fixes below, a live probe streamed synthesized speech through the
  production STT object and received `FINAL_TRANSCRIPT` plus `END_OF_SPEECH` two seconds after the
  speech ended; before the fix only partial transcripts arrived. Streamed websocket TTS through the
  production objects returned 2.48 s (HR, Sarah `EXAVITQu4vr4xnSDxMaL`) and 2.61 s (technical,
  Antoni) of audio. Speaker playback in a room was not observed by this probe.
- 21 September 2026: an agent joined a room and stayed silent. The job crashed with
  `InterviewNotFoundError` because an earlier interview was still `hr_active`, so R03 rejected the
  new record, but only after the agent had been dispatched. Fixes: `StartInterview` checks
  `InterviewStore.find_active()` before dispatching; the agent server runs
  `ReconcileInterruptedInterviews` at `dev`/`start` before it accepts jobs; and a job that ends
  before its interview finishes marks it `incomplete`. On the real database, startup logged
  `reconciled_interrupted_interviews=1 resumable=0` and the stuck interview became `incomplete`
  with reason "Interrupted process had no durable recovery checkpoint."

## Remaining completion path

1. Run one complete audible interview and capture evidence for speaker playback, both voices,
   sequential I/O ownership, full HR-to-Technical handoff, and final results.
2. Connect real room media to the recording sink and verify alignment, gaps, and restart behavior.
3. Finish production checkpoint/reconnect wiring and exercise recovery inside and beyond the
   fixed 120-second deadline.
4. Persist Technical case, difficulty, and hint decisions; complete live adaptive-policy tests.
5. Run live scoring calibration and prove delayed HR scoring does not affect Technical audio.
6. Re-run P10 acceptance and update this file only from executed evidence.

## Documentation disposition

- Keep `MAIN_PLAN.md`, `ARCHITECTURE.md`, and `plans/` as the normative product and phase specs.
- Keep `docs/RUNBOOK.md` for operations, `docs/USER_GUIDE.md` for the end-user walkthrough,
  `docs/ACCEPTANCE.md` for detailed scenario evidence, `docs/compatibility.md` for tool/provider
  evidence, and `docs/retention.md` for scheduled cleanup.
- Keep `SOURCES.md` for external source provenance.
- `CODEX_START.md` was removed because it was a one-time bootstrap prompt whose current-state
  claims had become stale; `AGENTS.md` plus this audit now provide the active execution guidance.

## Next ready slice

P02 production recording and P08 production checkpoint wiring can proceed without a successful
TTS request. The P00/P04/P10 audible gates are no longer blocked by the provider and should be run
next with `./run.sh`.
