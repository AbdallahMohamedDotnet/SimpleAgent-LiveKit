# Project structure and ownership

The project uses a packaged `src` layout on CPython 3.14. LiveKit Agents and the direct
ElevenLabs and OpenAI-compatible plugins are pinned to the 1.8.2 versions verified in P00. The
OpenAI-compatible plugin is configured as the OpenRouter transport; LiveKit Inference and the
starter template's AssemblyAI, Fish Audio, and cloud noise-cancellation defaults are intentionally
absent. Provider construction is tested offline, but provider access is not yet verified.

- `domain` owns immutable records, IDs, and states. It uses only the Python standard library.
- `application` owns use cases and small consumer-oriented ports. It imports the domain but no
  concrete adapter or vendor SDK.
- `adapters` implements ports. Fakes deliberately model lifecycle and failure behavior; the
  SQLite, WAV, provider-construction, and LiveKit stage adapters preserve the same typed
  boundaries.
- `entrypoints` parse operator input and delegate to use cases.
- `bootstrap.py` is the composition root and the only layer that selects concrete adapters.
- `settings.py` reads no environment variables itself. A process boundary passes a mapping,
  receives validated immutable settings, and injects them during construction.

The official `agent-starter-python` template was instantiated only in a temporary inspection
directory. Its single-file, cloud-oriented layout was not copied over this architecture. When the
real Agent Server entrypoint is added, its SDK callbacks and Agent subclasses belong under
`adapters/livekit/`; the entrypoint will construct them through `bootstrap.py`.

Each stage runtime owns only its stage lifecycle and must drain before it closes.
`TwoStageHandoffController` passes the same durable room SID and generated candidate identity to
both distinct runtimes, closes HR before starting technical I/O, and never gives a scoring
consumer room media access. `adapters/livekit/LiveKitStageRuntime` implements that boundary with
one `AgentSession`, binds RoomIO to the intended candidate identity, refuses a mismatched room SID,
and awaits full RoomIO cleanup without disconnecting or deleting the job-owned room. Agent Server
registration and dispatch-metadata composition remain future entrypoint work.

`adapters/sqlite/` now owns database connection policy, versioned migrations, SQL, and conversion
between rows and immutable boundary records. Every repository operation opens a configured
`aiosqlite` connection, enables foreign keys, WAL, and a busy timeout, completes one short read or
write transaction, and closes the connection. Provider or filesystem work must never occur inside
those transactions. `SqliteTranscriptStore` atomically freezes final turns and enqueues the unique
score task; `SqliteScoreTaskStore` owns lease claims and rejects stale completions.

`adapters/audio/` owns bounded asynchronous PCM writes and job-scoped WAV files. Stage segment
closure does not close the recorder. Manifests preserve track offsets, checksums, explicit gaps,
and incomplete/failure status; `SqliteRecordingManifestStore` makes them restartable. Synthetic
WAV playback is covered offline, while observable LiveKit capture remains blocked on host audio.

`domain/policies.py` owns monotonic stage timing and idle reminder decisions. Provider SDK option
mapping lives only in `adapters/providers/`; constructing those adapters performs no provider
request and is not evidence of account/model/voice access.

P08 adds durable recovery checkpoints and connection-attempt history through
`SqliteRecoveryStore`. `RecoverInterview` owns the fixed retry deadline and preserves remaining
active time; `ReconcileInterruptedInterviews` distinguishes resumable checkpoints from missing or
expired recovery state. Live job/controller wiring remains separate from these tested contracts.

`SqliteRetentionStore` prepares retryable deletion manifests without doing filesystem work inside
a database transaction. `LocalArtifactStore` deletes only regular files below its owned root and
rejects traversal or symlink paths. The cleanup use case deletes artifacts first, then dependent
database rows; scoring claims and completions reject expired or deletion-pending interviews.

P09 adds a small `ResultsReader` port with immutable list/detail/media DTOs. Its SQLite adapter
filters expired and deletion-pending interviews on every query. The web adapter owns presentation
formatting and HTML escaping, accepts only GET/HEAD, binds through validated localhost-only
settings, and resolves audio from a stored segment ID before reading a regular non-symlink file
under the configured recording root. It has no database write surface.

Available commands:

```text
interview dry-run --name "Candidate Name"
interview worker [--once]
interview cleanup
interview results
```

The available commands are the offline `dry-run` lifecycle, durable `worker` scoring process,
retryable `cleanup` retention pass, and localhost-only `results` viewer. Planned but unavailable
commands are `run` and `status`. See `docs/retention.md` for startup catch-up and local scheduler
instructions.
