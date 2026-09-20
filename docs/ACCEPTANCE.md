# P10 acceptance evidence

Statuses in this document mean: **PASSED** is backed by an executed check, **PARTIAL** has passing
evidence but lacks a required live or production path, and **BLOCKED** cannot be completed with the
current implementation or environment. Synthetic and media-disabled checks never count as real
microphone, speaker, or provider evidence.

## Requirement matrix

| ID | Status | Evidence and remaining gap |
|---|---|---|
| R01 | PASSED | Ubuntu 26.04.1 x86_64, CPython 3.14.4, uv 0.12.17, and the pinned dependency set are recorded in `docs/compatibility.md` and `uv.lock`. |
| R02 | PARTIAL | Local LiveKit Server 1.13.7, CLI 2.18.2, rooms, and RTC participants were exercised without cloud deployment. The runnable ROOM Agent Server entrypoint is not implemented. |
| R03 | PARTIAL | Generated IDs, name-only input validation, duplicate candidate-name safety, and one-active-interview rejection pass offline. No production candidate command exists. |
| R04 | PARTIAL | Application handoff and a real media-disabled RTC probe preserve room/candidate identity across two distinct AgentSession objects. Real audio ownership/drain remains blocked. |
| R05 | PARTIAL | Versioned neutral HR instructions/rubric require real situations and the four fixed competencies; dynamic live questioning/provider behavior is unverified. |
| R06 | PARTIAL | Versioned technical instructions/rubric cover the fixed general-backend topics; live adaptive interviewing is unverified. |
| R07 | PARTIAL | Junior-first difficulty and one-hint policy tests pass. Live different-case generation and durable case/hint capture are incomplete. |
| R08 | PARTIAL | Fake-clock tests prove both 300-second policies, completion of an answer in progress, overrun recording, and no later question. Live speech-boundary behavior is unverified. |
| R09 | PARTIAL | Settings and prompts enforce English and scoring resources exclude grammar/accent/fluency. Provider output is unverified. |
| R10 | PARTIAL | Genuine-idle, five-second reminder, debounce, and 20-second requested-thinking policies pass. Live VAD, barge-in, and interruption behavior are blocked. |
| R11 | BLOCKED | ElevenLabs 1.8.2 STT/TTS adapters construct offline with distinct voices. Keys, two verified voice IDs, streaming media, PortAudio, and a terminal RTC client are unavailable here. |
| R12 | BLOCKED | OpenRouter construction and fixed Sonnet 5 model configuration pass offline. Account/model access and every live LLM task are unverified. |
| R13 | PARTIAL | Snapshot/task enqueue is transactional, scoring has no room I/O, and handoff does not await scoring. Deliberately slow live HR scoring during technical speech is unverified. |
| R14 | PARTIAL | Strict 1–5 evidence validation, equal stage averages, null exclusion, coverage, and separate stage results pass offline. Provider calibration is blocked. |
| R15 | PARTIAL | SQLite turns/snapshots/events/scores and synthetic playable WAV manifests survive restart. Real observable room recording, case/hint evidence, and media alignment are incomplete. |
| R16 | PASSED | Exact 30-day UTC hiding/deletion, artifacts, retryable failures, worker races, startup command, and installed daily user timer pass locally. Provider-side retention is outside local control. |
| R17 | PASSED | The loopback-only read-only HTML viewer passes escaping, expired-data, media-ID, traversal, duplicate-name, incomplete/pending/failed, and POST rejection tests. |
| R18 | PARTIAL | Fake-clock transient/permanent recovery and one persisted 120-second deadline pass. Production checkpoint emission and real track/participant/recorder rebinding are incomplete. |
| R19 | PASSED | No in-agent recording-consent flow is present; operator documentation still describes local evidence handling. |

## Final acceptance scenarios

| Scenario | Status | Evidence and remaining gap |
|---|---|---|
| Terminal microphone/playback in one local room | BLOCKED | ALSA enumerates capture/playback hardware, but PortAudio and the terminal RTC client are absent; zero audio tracks were published. |
| Same-room two-session handoff without overlapping I/O | PARTIAL | Same SID/identity and distinct sessions passed in a real signaling room with media disabled; audible drain and ownership remain unverified. |
| Slow HR scoring while technical conversation continues | PARTIAL | Queueing and separation of score worker from voice I/O pass; no production technical conversation exists. |
| Deadline, final answer, interruption, idle, thinking time | PARTIAL | Deterministic policy coverage passes; real VAD/STT/TTS event behavior is blocked. |
| Adaptive cases, hints, real-situation HR, English-neutral scoring | PARTIAL | Typed policies/prompts/rubrics pass; live generation, capture, and provider calibration remain. |
| Evidence-valid independent scores and coverage | PARTIAL | Strict parser, durable worker, restart, evidence IDs, null arithmetic, and UI rendering pass with local deterministic assessment; live Sonnet 5 is blocked. |
| Restartable evidence/audio and honest recovery gaps | PARTIAL | SQLite and synthetic WAV/recovery manifests survive restart; real captured audio and live reconnect are blocked. |
| 120-second failure is incomplete; score failure is independent | PARTIAL | Offline state/retry behavior passes; production controller wiring remains. |
| Expiry hides and deletes all owned local data | PASSED | Fake-clock exact-boundary, viewer hiding, safe artifact deletion, failure retry, and worker race tests pass. |
| Safe localhost results viewer | PASSED | Real ephemeral HTTP smoke returns list/detail/media 200 and POST 405 with escaped untrusted content and ID-authorized media. |
| Quality and architecture gates | PASSED | See the dated P10 report in `PROGRESS.md` for the exact commands and counts from the latest run. |
| Reproducible operating instructions | PARTIAL | `docs/RUNBOOK.md` covers every currently runnable command and explicitly identifies the absent production run path. |

## Known limitations of the screening result

The intended interview is roughly ten active minutes. It can support only a limited, evidence-based
screening observation, not a complete measure of seniority. Missing evidence remains null, assisted
work is identified, and HR and technical results remain separate. The application must not infer
mental health, personality, deception, or capability from voice qualities, and it makes no hiring
decision.

Strong, weak, assisted, and incomplete assessment calibration through the required live Sonnet 5
provider has not been run. Until provider access, physical audio, production controller/Agent
Server wiring, and the terminal RTC client are available, P10 remains `IN_PROGRESS / BLOCKED`.
