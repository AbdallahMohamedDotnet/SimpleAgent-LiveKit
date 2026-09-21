# P00 — Compatibility and local feasibility

Current status is tracked only in [PROGRESS.md](../PROGRESS.md).

**Read first:** [AGENTS.md](../AGENTS.md), [MAIN_PLAN.md](../MAIN_PLAN.md), [ARCHITECTURE.md](../ARCHITECTURE.md), [PROGRESS.md](../PROGRESS.md).

**Dependencies:** None.

**Requirements covered:** R01, R02, R04, R11, R12.

## Current state

Local toolchain discovery, checksum-verified LiveKit CLI/server installation, room signaling, SDK
lifecycle inspection, and sequential-session probes are complete. A project-local PortAudio
runtime later exposed host devices: a terminal candidate published microphone audio, ElevenLabs
STT transcribed it, and OpenRouter generated the opening HR question. ElevenLabs TTS returned HTTP
402, so generated agent audio, speaker playback, both-voice handoff, interruption, and real-media
drain/capture remain blocked. Exact current evidence is in
[docs/compatibility.md](../docs/compatibility.md) and [PROGRESS.md](../PROGRESS.md).

## Objective and scope

Establish the actual Ubuntu, Python, LiveKit, audio and provider capabilities before relying on them in implementation. This phase creates small feasibility probes and records their results, not the complete application.

## Implementation tasks

1. Inspect exact Ubuntu version, CPU architecture, installed Python/tool versions, microphone/speaker devices, permissions and the audio backend. Do not assume that “Ubuntu 26” fully identifies the environment.
2. Select a supported Python environment using uv. Inspect or install LiveKit CLI and local server within applicable permissions. Record versions and local binding. Do not create a cloud project.
3. Inspect `lk --help`, `lk agent --help`, `lk room join --help`, and dispatch/project command help. Record actual supported command syntax.
4. Start a local server, configure a local CLI project, create a real room and inspect participants. Distinguish a room-connected test from roomless console mode.
5. Verify bidirectional terminal microphone/speaker audio in that room. If the installed CLI lacks that route, make the smallest Python RTC terminal participant probe using local device I/O. Keep CLI room/dispatch management. No browser interview workaround.
6. Verify Sonnet 5 account access, streaming, tool handling and structured scoring response behavior using locally injected credentials. Check supported request parameters. Never silently substitute a model.
7. Verify ElevenLabs streaming STT, TTS and both configured voices. Use direct plugins; remove template defaults that call other providers.
8. Inspect and probe session drain/close behavior: can one session release I/O while the job and room remain alive for a second session? Record the exact SDK methods and any custom RoomIO ownership needed.
9. Probe capture of actual published agent/candidate audio, interruption behavior and timestamp alignment. Document what can be proven about playback and what remains uncertain.
10. Write `docs/compatibility.md` with versions, commands, evidence, pass/fail/blocked status and source references. Retain only useful probes; do not turn throwaway code into production architecture.

## Deliverables

- Local compatibility report with a selected toolchain and known CLI syntax.
- Demonstrated room-connected audio, or a clearly blocked hardware gate.
- Provider/voice checks and a documented two-session lifecycle strategy.
- Any temporary probes isolated from the eventual domain/application packages.

## Acceptance gate

- A real room and two-way audio are evidenced by IDs/events and an operator check, not only console output.
- Credentials are never printed or committed. Missing credentials yield BLOCKED, not a fake pass.
- Model/voice access and session cleanup behavior are proven or explicitly unresolved.
- Independent scaffolding may proceed with fakes if a live gate is blocked; no dependent live acceptance is claimed.

## Engineering review

Apply AGENTS.md to this phase. Keep business rules in domain/application code, infrastructure in adapters and construction in bootstrap. Use typed contracts and meaningful behavioral tests. Preserve cancellation, resource ownership, idempotency and accurate failure reporting. Do not introduce unused abstractions or expand the product scope.

## Handoff to the next phase

Update PROGRESS.md with implementation status, verification status, changed files, commands actually run, evidence and unresolved risks. Clearly distinguish tested behavior from assumptions. Do not mark this phase complete simply because its files exist.

## Codex task prompt

> Implement P00: Compatibility and local feasibility. Read the repository instructions and this subplan first. Verify prerequisites, implement the smallest complete changes satisfying its acceptance gate, and run relevant checks. Follow SOLID and the dependency rules in AGENTS.md and ARCHITECTURE.md. Preserve all fixed requirements. Record actual results and blockers in PROGRESS.md. If assigned only this phase, stop after its completion report; if assigned the whole project, continue to the next ready phase. Never present unverified live behavior as tested.
