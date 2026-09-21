# Project completion audit

Last reconciled: 21 September 2026.

This is the single authoritative implementation-status summary for `MAIN_PLAN.md`,
`ARCHITECTURE.md`, and `plans/P00` through `plans/P10`. The plan files remain the normative
specification. Detailed operating instructions and reproducible evidence remain in
`docs/RUNBOOK.md`, `docs/ACCEPTANCE.md`, and `docs/compatibility.md`.

## Verdict

The project is **not complete**. The local application, production ROOM Agent Server, terminal
RTC candidate, persistence, scoring worker, retention workflow, operator console, and results
viewer are implemented far enough for the complete offline suite to pass. A real microphone
track reached ElevenLabs STT, and OpenRouter generated the opening HR question. The configured
ElevenLabs account returned HTTP 402 for TTS, so agent audio, speaker playback, the audible
two-stage handoff, and the full end-to-end interview remain blocked.

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
| P08 recovery/retention | IN_PROGRESS | PARTIAL | Fixed 120-second recovery budget, checkpoints/reconciliation contracts, exact 30-day expiry, safe retryable artifact deletion, worker races, cleanup CLI, and daily user timer pass locally. | Wire checkpoints/recovery into the production live controller and verify real reconnect, track rebind, recorder segmentation, and timeout behavior. |
| P09 results | IMPLEMENTED | PASSED | Expiry-safe read DTOs, escaped localhost HTML, separate HR/Technical results, evidence links, pending/null/failure display, and ID-authorized media pass HTTP/security tests. | None within P09. |
| P10 acceptance/runbook | IN_PROGRESS | BLOCKED | Runbook, user guide, operator launch/status UI, terminal commands, offline acceptance smoke, architecture gate, and quality suite pass. | Complete all blocked live scenarios after TTS is available, then record full same-room handoff, scoring concurrency, recovery, recording, and final results evidence. |

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
| R11 | BLOCKED | ElevenLabs STT is live-verified; TTS returns HTTP 402, so both voices and speaker playback are blocked. |
| R12 | PARTIAL | OpenRouter Sonnet 5 generated the opening question live; live scoring and all-task verification remain. |
| R13 | PARTIAL | HR snapshot/task enqueue precedes Technical and scoring owns no room I/O; slow live scoring concurrency is unverified. |
| R14 | PARTIAL | Evidence validation, 1–5/null rules, coverage, and independent stage scores pass offline; live calibration remains. |
| R15 | PARTIAL | Records and synthetic WAV artifacts persist; real room recording and technical case/hint evidence are incomplete. |
| R16 | PASSED | Exact 30-day hiding/deletion, retry behavior, worker races, CLI, and scheduled local cleanup pass. |
| R17 | PASSED | The localhost-only read-only HTML viewer passes functionality and security checks. |
| R18 | PARTIAL | Recovery policy and persistence pass offline; production reconnect/checkpoint/media recovery is incomplete. |
| R19 | PASSED | No in-agent consent step is present, as required. |

Detailed scenario evidence is retained in `docs/ACCEPTANCE.md`.

## Implemented operator workflow

The repository exposes:

```text
interview config-check
interview dry-run --name "Candidate Name"
interview run --name "Candidate Name" [--input-device DEVICE] [--output-device DEVICE]
interview join --interview-id ID [--input-device DEVICE] [--output-device DEVICE]
interview devices
interview worker [--once]
interview cleanup
interview control
interview results
interview-agent dev --no-reload
```

The control console is operator-only and bound to `127.0.0.1`; candidate microphone and speaker
I/O remain in the terminal client. SQLite contains interview evidence and local files contain
recording artifacts. The scoring worker has no room-audio access.

## Latest verification

The following checks were executed against the current working tree on 21 September 2026:

```text
UV_CACHE_DIR=/tmp/livekit-cli-uv-cache .tools/bin/uv run ruff format --check .
  PASS: 122 files already formatted
UV_CACHE_DIR=/tmp/livekit-cli-uv-cache .tools/bin/uv run ruff check .
  PASS
UV_CACHE_DIR=/tmp/livekit-cli-uv-cache .tools/bin/uv run mypy src
  PASS: 67 source files
UV_CACHE_DIR=/tmp/livekit-cli-uv-cache .tools/bin/uv run pytest
  PASS: 52 tests in 1.77 seconds
UV_CACHE_DIR=/tmp/livekit-cli-uv-cache .tools/bin/uv run python scripts/p10_offline_acceptance_smoke.py
  PASS: offline_only; provider_request_made=false; live_audio_verified=false
bash -n scripts/run_local.sh
  PASS
```

The restricted sandbox stalled at the known SQLite integration point. The pytest suite and
offline acceptance smoke were therefore rerun with ordinary host permissions and passed. No new
provider request was made during this audit.

Previously verified live evidence:

- A project-local PortAudio runtime enumerated PipeWire/ALSA devices.
- A terminal candidate published an unmuted microphone track in room `RM_vxgMgPepn2Xo`.
- ElevenLabs realtime STT produced partial and final candidate text.
- OpenRouter generated and persisted the opening HR question.
- A direct ElevenLabs TTS probe returned non-retryable HTTP 402 `Payment Required` and produced no
  audio frames.

## Remaining completion path

1. Enable billing or credits for the configured ElevenLabs account without changing provider,
   model, or voices.
2. Run one complete audible interview and capture evidence for speaker playback, both voices,
   sequential I/O ownership, full HR-to-Technical handoff, and final results.
3. Connect real room media to the recording sink and verify alignment, gaps, and restart behavior.
4. Finish production checkpoint/reconnect wiring and exercise recovery inside and beyond the
   fixed 120-second deadline.
5. Persist Technical case, difficulty, and hint decisions; complete live adaptive-policy tests.
6. Run live scoring calibration and prove delayed HR scoring does not affect Technical audio.
7. Re-run P10 acceptance and update this file only from executed evidence.

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
TTS request. The blocked P00/P04/P10 audible gates should be rerun as soon as ElevenLabs billing is
enabled.
