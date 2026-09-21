# P03 — One job, two sessions and same-room handoff

Current status is tracked only in [PROGRESS.md](../PROGRESS.md).

**Read first:** [AGENTS.md](../AGENTS.md), [MAIN_PLAN.md](../MAIN_PLAN.md), [ARCHITECTURE.md](../ARCHITECTURE.md), [PROGRESS.md](../PROGRESS.md).

**Dependencies:** P01–P02; P00 lifecycle/audio gate for live verification.

**Requirements covered:** R03, R04, R13.

## Current state

The application controller implements ordered HR drain/close, atomic HR snapshot/task creation,
immutable attributed `HandoffPayload`, and technical startup with the same persisted room SID and
candidate identity but a distinct session reference. Concurrent duplicate handoff calls are
idempotent, a second active interview is rejected atomically, and a blocked fake scoring consumer
does not own technical I/O. A production `LiveKitStageRuntime` now validates the persisted room
SID, binds RoomIO to the intended candidate identity, drains speech/final transcripts, awaits the
full RoomIO cleanup barrier, and never closes or deletes the job-owned room. Adapter tests and a
local real-RTC signaling probe pass across two distinct AgentSessions in one room. The ROOM Agent
Server now validates durable dispatch metadata, claims a real local dispatch, waits for the exact
candidate identity, runs the two-stage coordinator, and completes both independent score tasks.
Candidate microphone audio, ElevenLabs STT, and the opening OpenRouter response are live-verified.
ElevenLabs TTS, audible two-stage handoff, final-speech drain, and physical speaker output remain
unverified; therefore the full acceptance gate is not claimed.

## Latest continuation note — 20 September 2026

Added the production stage adapter, lifecycle/error checks, integration coverage, and
`scripts/p03_livekit_handoff_probe.py`. The first real-room probe exposed that LiveKit emits its
session close event before RoomIO cleanup completes; the adapter now awaits `aclose()` as a second
barrier before technical startup. The corrected probe preserved room SID `RM_AER5uYqo3yXS`, the
candidate connection, and distinct HR/technical session references. It made no provider call and
carried no microphone media. Ruff, strict mypy, and all 17 tests pass. A non-fatal LiveKit FFI
cleanup warning occurred in the synthetic probe and remains live-SDK follow-up evidence, not a
passed physical media gate.

## Objective and scope

Implement application-controlled transfer between two distinct AgentSessions without disconnecting the candidate or waiting for HR scoring. Keep initial agents simple so lifecycle correctness is independently testable.

## Implementation tasks

1. Register a local Agent Server with the verified ROOM job configuration and dispatch name. Claim an active-interview lock atomically; reject a second active interview safely.
2. Pass generated interview/candidate IDs through dispatch metadata and load the name from storage. Bind only the intended candidate; ignore a recording observer.
3. Implement controller transitions and explicit resource ownership. Keep SDK callbacks thin and translate them into typed application events.
4. Start HR session against the job's room connection. Ensure the entrypoint stays alive for both stages.
5. Implement the ordered handoff protocol: stop new questions, drain speech and final transcripts, close HR I/O only, commit snapshot plus task, start the distinct technical session in the same room.
6. Pass attributed HR Q/A through HandoffPayload. Do not pass HR system instructions, tools or a mutable chat-history object.
7. Prove that a deliberately slow fake scoring consumer does not delay technical startup. Real LLM assessment is P07.
8. Make the transition idempotent. Duplicate end-stage events must not create two technical sessions or scoring tasks.
9. Configure stage close/disconnect handling so later recovery is possible. Job shutdown and room deletion occur only at overall interview teardown.
10. Add lifecycle tests with fake runtimes plus a real local-room test. Record room SID, candidate identity, distinct session references and I/O ownership transitions.

## Deliverables

- Application controller/handoff use cases and LiveKit runtime adapter.
- Typed HandoffPayload and durable transition events.
- Evidence of a two-session same-room transition, or a precisely documented blocked live gate.

## Acceptance gate

- Same room SID/candidate identity across normal handoff; two distinct sessions and agents.
- HR final answer is included in the frozen snapshot.
- At most one conversational I/O owner; no double STT consumption or overlapping speech.
- HR assessment task exists before technical startup, but its result is not awaited.
- Closing HR never terminates the entire job.

## Engineering review

Apply AGENTS.md to this phase. Keep business rules in domain/application code, infrastructure in adapters and construction in bootstrap. Use typed contracts and meaningful behavioral tests. Preserve cancellation, resource ownership, idempotency and accurate failure reporting. Do not introduce unused abstractions or expand the product scope.

## Handoff to the next phase

Update PROGRESS.md with implementation status, verification status, changed files, commands actually run, evidence and unresolved risks. Clearly distinguish tested behavior from assumptions. Do not mark this phase complete simply because its files exist.

## Codex task prompt

> Implement P03: One job, two sessions and same-room handoff. Read the repository instructions and this subplan first. Verify prerequisites, implement the smallest complete changes satisfying its acceptance gate, and run relevant checks. Follow SOLID and the dependency rules in AGENTS.md and ARCHITECTURE.md. Preserve all fixed requirements. Record actual results and blockers in PROGRESS.md. If assigned only this phase, stop after its completion report; if assigned the whole project, continue to the next ready phase. Never present unverified live behavior as tested.
