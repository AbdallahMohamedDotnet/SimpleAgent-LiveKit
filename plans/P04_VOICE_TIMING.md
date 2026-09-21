# P04 — Voice providers, deadlines, interruption and idle handling

Current status is tracked only in [PROGRESS.md](../PROGRESS.md).

**Read first:** [AGENTS.md](../AGENTS.md), [MAIN_PLAN.md](../MAIN_PLAN.md), [ARCHITECTURE.md](../ARCHITECTURE.md), [PROGRESS.md](../PROGRESS.md).

**Dependencies:** P03; verified provider/device access for live tests.

**Requirements covered:** R08–R12, R18.

## Current state

The pinned SDK adapter constructs Sonnet 5 through OpenRouter and realtime ElevenLabs STT plus
separate HR/technical TTS instances with explicit voice IDs. Configuration enforces English,
300-second stages, five-second idle checks, and the 20-second thinking hold. Pure monotonic
policies suppress new questions at the deadline, allow the current answer to finish, record
overrun, exclude recovery, and debounce genuine-idle reminders. Construction and fake-clock tests
pass without network access. A supervised LiveKit transcript bridge now persists final candidate
transcriptions and attributed interviewer turns, marks generated agent delivery as uncertain, and
flushes before snapshot finalization. Live microphone publication, ElevenLabs STT, and the opening
OpenRouter response are verified. TTS/playout, live VAD/barge-in, deadline, idle, and thinking-time
behavior remain unverified.

## Objective and scope

Integrate the chosen providers and implement deterministic conversation timing independently of SDK event quirks.

## Implementation tasks

1. Implement provider adapters/factories for Sonnet 5 through OpenRouter and ElevenLabs streaming STT/TTS. Set distinct voice IDs explicitly and keep secrets in validated settings.
2. Map domain configuration to the verified SDK options in the adapter. Do not pass unsupported model parameters because an old template does.
3. Configure turn handling and any local VAD required by the chosen SDK. A local speech detector is not an additional cloud provider.
4. Implement a monotonic active-stage timer starting at the first substantive question. Exclude greeting, handoff and infrastructure recovery. Ordinary thinking counts.
5. On the five-minute deadline, prevent new questions. Allow the current-question answer to complete, then transition/end. Record overrun; do not introduce an unrequested hard cut-off.
6. Handle barge-in by canceling outstanding speech/playout according to SDK semantics. Record interruption and what delivery can actually be observed.
7. Implement one debounced check-in after five seconds of genuine idle. Suppress it while speaking/generating and honor an explicit thinking extension; distinguish this from endpointing.
8. Keep spoken replies concise and English only. Do not speak assessment scores or private system instructions.
9. Add fake-clock tests for deadline/idle/recovery interactions and a real-device interruption test. Test pauses in mid-answer so normal hesitation is not mistaken for completion.

## Deliverables

- Provider adapters, validated voice settings and timing use cases.
- English voice policy and typed speech/idle/interruption events.
- Deterministic timing tests plus recorded live verification notes.

## Acceptance gate

- Correct distinct voices and required model/providers are used.
- Interruptions stop pending speech without corrupting transcript evidence.
- Five seconds is an idle reminder threshold, not a forced end-of-answer rule.
- In-progress answers finish after 300 seconds; no new questions start after the deadline.
- No synchronous I/O blocks the audio event loop.

## Engineering review

Apply AGENTS.md to this phase. Keep business rules in domain/application code, infrastructure in adapters and construction in bootstrap. Use typed contracts and meaningful behavioral tests. Preserve cancellation, resource ownership, idempotency and accurate failure reporting. Do not introduce unused abstractions or expand the product scope.

## Handoff to the next phase

Update PROGRESS.md with implementation status, verification status, changed files, commands actually run, evidence and unresolved risks. Clearly distinguish tested behavior from assumptions. Do not mark this phase complete simply because its files exist.

## Codex task prompt

> Implement P04: Voice providers, deadlines, interruption and idle handling. Read the repository instructions and this subplan first. Verify prerequisites, implement the smallest complete changes satisfying its acceptance gate, and run relevant checks. Follow SOLID and the dependency rules in AGENTS.md and ARCHITECTURE.md. Preserve all fixed requirements. Record actual results and blockers in PROGRESS.md. If assigned only this phase, stop after its completion report; if assigned the whole project, continue to the next ready phase. Never present unverified live behavior as tested.
