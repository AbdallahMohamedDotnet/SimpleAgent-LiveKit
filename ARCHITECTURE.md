# Architecture and Contracts

This document is the normative target design. AGENTS.md defines coding discipline; MAIN_PLAN.md
defines product requirements. P00 verified the selected local versions and relevant SDK
signatures; live provider/media behavior remains blocked. `PROGRESS.md` is authoritative for what
is currently implemented and verified.

## 1. Dependency direction

| Layer | Allowed dependencies | Prohibited responsibilities |
|---|---|---|
| `domain` | Python standard library | SDK calls, SQL, filesystem access, HTTP, environment reads |
| `application` | domain, application ports, standard library | Concrete provider/LiveKit/SQLite/web imports |
| `adapters` | domain, application ports, relevant infrastructure libraries | Redefining timing/scoring/retention policy |
| `entrypoints` | use cases and composition root | Business rules and direct SQL |
| `bootstrap` | All layers for construction | Interview orchestration or scoring logic |

A small Protocol at the boundary is sufficient. Do not build a dependency-injection framework. Adapters translate exceptions and data into stable application contracts.

## 2. Target project map

Create modules when needed, not empty placeholder files for the entire map.

Current implementation: project/tooling, domain models and policies, application ports, offline
lifecycle/handoff and scoring-worker use cases, fakes, SQLite evidence/result repositories,
bounded WAV recording, voice and text-assessment provider construction, settings, CLI dry run and
worker commands, and unit/contract/integration tests exist. Recovery orchestration, retention
cleanup, results queries/UI, Agent Server/operator run command, and acceptance tests do not yet
exist. `adapters/audio/` currently records supplied observable PCM; it is not connected to a real
room media source.

| Path | Responsibility |
|---|---|
| `pyproject.toml`, `uv.lock` | Reproducible dependencies and development checks |
| `.env.example`, `.gitignore` | Document settings and exclude secrets/data |
| `src/interview_app/domain/models.py` | IDs, records, typed states and value objects |
| `src/interview_app/domain/policies.py` | Pure timing, score averaging, difficulty and expiry policies |
| `src/interview_app/application/ports/` | Small consumer-oriented infrastructure contracts |
| `src/interview_app/application/interview.py` | Interview lifecycle use cases and controller |
| `src/interview_app/application/handoff.py` | Ordered idempotent stage transition |
| `src/interview_app/application/timing.py` | Clock-based timer and idle use cases |
| `src/interview_app/application/scoring.py` | Snapshot assessment and output validation use cases |
| `src/interview_app/application/recovery.py` | Checkpoint and recovery coordination |
| `src/interview_app/application/retention.py` | Expiry selection and deletion orchestration |
| `src/interview_app/application/results.py` | Read-only result queries/DTOs |
| `src/interview_app/adapters/livekit/` | Agent Server, session factory, RoomIO, HR/technical Agent subclasses, RTC events |
| `src/interview_app/adapters/providers/` | ElevenLabs and OpenRouter integration |
| `src/interview_app/adapters/sqlite/` | Migrations, repositories and task queue |
| `src/interview_app/adapters/audio/` | Terminal device I/O and recording |
| `src/interview_app/adapters/web/` | Minimal results server and escaped templates |
| `src/interview_app/entrypoints/` | CLI, worker, agent, results and cleanup commands |
| `src/interview_app/bootstrap.py` | Dependency construction and resource ownership |
| `src/interview_app/settings.py` | Validated boundary configuration |
| `src/interview_app/resources/prompts/` | Versioned HR, technical, scoring and summary prompts |
| `src/interview_app/resources/rubrics/` | Versioned competency definitions and anchors |
| `tests/unit`, `tests/contracts`, `tests/integration`, `tests/acceptance` | Tests grouped by purpose |
| `docs/`, `scripts/`, `data/` | Runbook/evidence, thin operational scripts, ignored runtime data |

## 3. Runtime ownership

- Local LiveKit Server owns room/participant/media infrastructure.
- Agent Server accepts one interview job at a time using a stable dispatch name such as `interview-agent`.
- One job and its JobContext own the room connection across HR and technical stages in the normal path.
- The application controller owns state transitions and the active stage timer. The Agent cannot directly change time or write scores.
- Each AgentSession owns its own STT/LLM/TTS conversation lifecycle. Only one session owns conversational RoomIO at any moment.
- A job-scoped recorder outlives individual sessions. A distinct recording participant is permissible if required for actual media capture, but it must never be linked as the candidate or dispatch another interview job.
- A separate scoring process owns database task leases and LLM assessment requests. It does not depend on a live voice job.
- The results server owns read-only queries. A scheduled cleanup process owns retention execution.

Define which owner closes every task/connection. Stage teardown must not accidentally call job shutdown, delete the room or cancel the other process's persisted scoring work.

## 4. Core boundary contracts

| Contract | Required semantics |
|---|---|
| `Clock` | Monotonic elapsed time and UTC now; deterministic fake supports advancement without sleeping |
| `StageRuntime` | Start against an existing connection, observe finalized turns, drain, close stage only; never expose SDK types to domain |
| `TranscriptStore` | Append idempotent events/turns; finalize immutable revision; read attributed HR Q/A |
| `InterviewStore` | Create ID, transition state with concurrency guard, checkpoint and claim active-interview ownership |
| `ScoreTaskStore` | Enqueue with snapshot atomically, claim with lease, renew/release, complete idempotently |
| `AssessmentModel` | Assess a validated snapshot against a versioned rubric; return typed result or classified failure |
| `RecordingSink` | Start, segment, record gaps, flush/close, return recording manifest; bounded buffering |
| `ResultsReader` | Return read-only DTOs; enforce expiry and expose no mutation methods |
| `ArtifactStore` | Resolve owned paths safely, delete idempotently, enumerate manifest entries |

Use precise contracts in code only when a consumer exists. Do not create one interface per function mechanically. Runtime events should be typed records, not arbitrary dictionaries.

## 5. Handoff protocol

1. At the HR deadline, stop generating new questions and allow the in-progress/current-question answer to finish.
2. Deliver a short transition message, drain pending speech and final transcript events, then close HR I/O/session without closing the room/job.
3. Finalize HR snapshot. Commit snapshot plus unique scoring task atomically.
4. Allow the scoring worker to claim the task independently; the controller never awaits the HR result.
5. Build the technical session and Agent with a distinct voice. Bind the same candidate identity and existing room connection after HR releases I/O.
6. Inject HR Q/A as attributed reference data. Do not transplant HR tools, system instructions or scoring conclusions.
7. Start technical questioning and its independent timer. Persist transition ID and stage start.

`HandoffPayload` contains interview_id, candidate display name, candidate identity, source stage ID, transcript snapshot ID/hash, attributed Q/A references, and completed-stage status. Avoid mutable shared chat history. The full five-minute HR transcript should ordinarily fit; if the verified model context requires truncation, record what was omitted and preserve the complete stored transcript.

Handoff is application orchestration between two sessions. A same-session Agent handoff API is not a substitute. Verify SDK stage cleanup in a real room before treating this design as implemented.

## 6. State and time

Conversation states: CREATED, WAITING_FOR_PARTICIPANT, HR_ACTIVE, HR_DRAINING, HANDOFF, TECH_ACTIVE, TECH_DRAINING, INTERVIEW_FINISHED, INCOMPLETE. RECOVERING also stores its previous state and recovery deadline. Assessment state is separate per stage: PENDING, RUNNING, SUCCEEDED, FAILED_RETRYABLE, FAILED_FINAL.

Time begins with the first substantive question. Count active conversation and normal thinking; exclude infrastructure outages, greeting and handoff. At 300 seconds, suppress new questions and finish the current answer. Save active duration and overrun. Do not impose a new hard overrun limit without a product decision.

Five-second idle is a check-in policy, not end-of-speech detection. Suppress it while either participant speaks, while the agent is legitimately generating, or while an explicit thinking extension applies. Debounce reminders. End-of-turn and barge-in use the verified SDK speech/turn mechanisms.

An outage creates one 120-second wall-clock deadline covering related retries; it does not reset for each request. Preserve remaining active time. Permanent configuration errors fail promptly. On timeout preserve partial evidence and mark the conversation incomplete. Scoring-only failures do not interrupt an otherwise healthy interview.

A normal reconnect attempts to retain room identity. A server crash may destroy Room SID; reusing its name does not preserve the original live room. Record new connection attempts and restore saved stage state honestly. Durable checkpoints cannot recover unsaved words or audio.

## 7. Target data model

Implemented tables currently include `interviews`, `stages`, `turns`, `snapshots`, `score_tasks`,
`recordings`, `recording_segments`, and `events`. The remaining rows below describe the required
end state and must not be read as existing migrations.

| Table | Key data/invariants |
|---|---|
| `interviews` | Generated ID, name, room name/SID, candidate identity, status, start/expiry, config version |
| `stages` | ID, interview ID, HR/TECH kind, session reference, state, time accounting |
| `turns` | ID, stage, speaker, text, interim/final, timestamps, interrupted and delivery certainty |
| `cases` | Stage, question turn, competency tags, difficulty, difficulty-change rationale |
| `hints` | Case/turn IDs, content, timing, assistance classification |
| `events` | Idempotent event ID, interview/stage, type, validated payload, timestamp |
| `recordings` | Owned relative path, speaker/track, time offsets, duration, gaps, checksum/status |
| `snapshots` | Immutable stage transcript revision/hash and final assessment input |
| `score_tasks` | Snapshot, rubric version, status, attempts, lease owner/expiry, retry time, failure |
| `stage_scores` | Stage/task version, model, rubric version, separate average or null, summary |
| `competency_scores` | Competency, 1–5 or null, rationale, support/limitations, difficulty and assistance |
| `score_evidence` | Competency score, final turn ID, exact span/quote, role of evidence |
| `checkpoints` | Stage, previous state, remaining time, last committed turn, recovery metadata |
| `deletion_jobs` | Expired interview, cleanup phase, manifest, attempts and error; avoid keeping candidate content after deletion |

Use parameterized SQL, foreign keys, explicit migration versions, short transactions, WAL, and busy timeouts. A single-interview limit does not remove concurrency between the worker, viewer, recorder and controller. No network call inside a transaction. Filesystem deletion and database deletion need a retryable workflow, not a pretend cross-system transaction.

## 8. Scoring contract

HR competencies: collaboration, ownership, feedback reception, conflict handling. Technical competencies: APIs, databases, debugging, system design, reasoning/problem-solving/decision justification.

Each competency contains a score in 1–5 or null, assessment status, evidence turn references, concise justification, limitations, and assistance/difficulty when relevant. Null means unassessed or insufficient evidence, never zero.

Stage average = sum of assessed competency scores / count of assessed competencies. When count is zero, average is null. Display coverage alongside the average. HR and technical scores remain separate.

Initial anchors: 1 = evidence of fundamental weakness; 2 = partial performance with clear gaps; 3 = sound demonstrated fundamentals; 4 = strong independent performance with trade-offs; 5 = advanced independent performance under meaningful complexity. These need competency-specific examples and calibration. A correct easy answer does not establish advanced ability. Do not subtract a fixed point merely because a hint was used; distinguish independent and assisted evidence.

The assessor uses fresh context, the immutable relevant stage snapshot and the rubric. Validate schema, IDs, exact quoted spans, unique competencies and score bounds. Never fabricate evidence or treat an HR claim as proven technical skill. Return concise evidence-based rationale, not a request for private model reasoning. Malformed responses receive bounded retries and an explicit failure if unresolved.

## 9. Recording and retention

Capture actual candidate and agent media with aligned timestamps, separate segments/tracks and optional combined playback. Raw generated TTS may contain canceled speech; it is not authoritative proof of delivery. Record observed publication/playback and uncertainty; network delivery to a remote speaker cannot always be proven. Audio gaps remain gaps.

Recorder survives stage handoff, starts a new segment on reconnect, uses bounded queues and reports disk/full/write failures. If complete recording cannot continue, preserve existing data and surface the failure; never claim “all audio saved.” Recovery of a failed recorder can use the same bounded recovery policy when capture is required.

Expiry is start time + 30 days. Use a local scheduled job plus startup catch-up. Exclude expired interviews from results immediately. Remove dependent rows, audio, snapshots, derived exports, temporary copies and candidate-bearing logs; make retries safe. Local deletion does not control provider retention or imply forensic erasure of an SSD. Do not create unmanaged backups.

## 10. Configuration and proposed commands

| Setting | Value/source |
|---|---|
| LIVEKIT_URL | Local URL, initially ws://127.0.0.1:7880 |
| LIVEKIT_API_KEY / LIVEKIT_API_SECRET | Supplied locally |
| OPENROUTER_API_KEY | Supplied locally |
| OPENROUTER_MODEL | anthropic/claude-sonnet-5; verify account access |
| ELEVEN_API_KEY | Supplied locally |
| ELEVEN_STT_MODEL | scribe_v2_realtime, subject to local compatibility check |
| ELEVEN_TTS_MODEL | Initial proposal eleven_turbo_v2_5; verify voice/model compatibility |
| HR_VOICE_ID / TECH_VOICE_ID | Distinct user-supplied values |
| INTERVIEW_LANGUAGE | en |
| HR_TARGET_SECONDS / TECH_TARGET_SECONDS | 300 / 300 |
| IDLE_CHECKIN_SECONDS / THINKING_HOLD_SECONDS | 5 / proposed 20 |
| RECOVERY_WINDOW_SECONDS / RETENTION_DAYS | 120 / 30 |
| MAX_ACTIVE_INTERVIEWS | 1 |
| SQLITE_PATH / RECORDINGS_DIR | Under an owned ignored data directory |
| RESULTS_HOST | 127.0.0.1 |

Proposed application interfaces: `interview run --name "Candidate Name"`, `interview worker`, `interview results`, `interview cleanup`, and `interview status`. These commands must be implemented; they are not built-in LiveKit commands. Do not print secrets in diagnostics.

Local startup order: verify settings; start local LiveKit; migrate SQLite; start worker/results; start Agent Server; create interview/room/dispatch through the CLI workflow; connect terminal candidate audio; conduct interview; drain and close; let scoring complete. Configure retention scheduling separately. Resolve actual CLI flags and executable entrypoints during P00/P01 and document tested commands in P10.
