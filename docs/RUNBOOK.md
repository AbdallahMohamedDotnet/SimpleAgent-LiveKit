# Ubuntu operator runbook

This runbook describes the commands that have actually been exercised in this checkout. The
offline workflow is reproducible. The production room-based interview is **not yet runnable**:
there is no `interview run`/Agent Server entrypoint or terminal RTC audio client, and this
execution environment has no accessible microphone or speaker. Do not treat the dry run as a
voice-interview pass.

## Verified toolchain and installation

The verified host is Ubuntu 26.04.1 LTS x86_64 with CPython 3.14.4, uv 0.12.17, LiveKit CLI
2.18.2, LiveKit Server 1.13.7, and LiveKit Agents/ElevenLabs/OpenAI-compatible plugins 1.8.2. The
project requires Python `>=3.14,<3.15`; Python packages and hashes are pinned in `uv.lock`.

From the repository root, install the locked development environment without privileged access:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv sync --frozen --group dev
```

The project-local `uv`, `lk`, and `livekit-server` binaries were installed and checksum-verified
during P00. If they are absent on another machine, follow the upstream installation links and
checksum procedure in `docs/compatibility.md`; do not copy credentials or binaries from another
operator's home directory.

## Configuration

Copy `.env.example` to the ignored `.env` file and fill values locally. The CLI does not load that
file automatically; export it in the operator shell with a trusted dotenv mechanism or export the
variables individually. Never commit `.env`.

The full live workflow requires local LiveKit development credentials, an OpenRouter key with
access to `anthropic/claude-sonnet-5`, an ElevenLabs key, and two different accessible ElevenLabs
voice IDs. The fixed language and timing values in `.env.example` must remain unchanged. Runtime
data defaults to `data/interviews.sqlite3` and `data/recordings/`.

Check only whether required values are present, without printing the secrets:

```bash
for name in LIVEKIT_API_KEY LIVEKIT_API_SECRET OPENROUTER_API_KEY ELEVEN_API_KEY HR_VOICE_ID TECH_VOICE_ID; do
  test -n "${!name:-}" && echo "$name=set" || echo "$name=missing"
done
```

## Current tested startup order

Run retention cleanup first:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview cleanup
```

Start the localhost results viewer in one terminal:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview results
```

Open `http://127.0.0.1:8080/results`. `RESULTS_HOST` is fixed to `127.0.0.1`; the viewer is not a
candidate interview UI.

With `OPENROUTER_API_KEY` set, start the durable scoring worker in another terminal:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview worker
```

Use `interview worker --once` for a single queue poll. A real provider call has not been verified
in this environment, so observe the worker result before relying on it.

The available candidate-name lifecycle check is provider-free:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview dry-run --name "Candidate Name"
```

It creates generated internal IDs and exercises two distinct fake stage runtimes. It creates no
room, audio, SQLite record, or provider request. The planned production startup sequence is local
LiveKit Server, ROOM Agent Server, cleanup, worker, results viewer, then a terminal RTC candidate;
that sequence cannot be executed until the missing Agent Server and terminal-audio entrypoints are
implemented.

## Local LiveKit control-plane probe

For signaling-only diagnostics, start the development server on loopback:

```bash
.tools/bin/livekit-server --dev --bind 127.0.0.1
```

In another terminal, inspect the configured local project and rooms:

```bash
.tools/bin/lk project set-default local-dev
.tools/bin/lk room list --json
```

Stop the server with `Ctrl-C`. This proves only the local control path. `lk room join` 2.18.2 does
not expose microphone/speaker device selection, while `lk agent console` is roomless and therefore
does not satisfy acceptance.

## Device selection and live audio gate

From a normal host session with PipeWire or ALSA access, list Agent console devices:

```bash
.tools/bin/lk agent console --list-devices
```

When a production terminal RTC client exists, it must expose explicit input and output selection,
publish a microphone track in the local room, play the subscribed agent track, and record the
selected device names plus LiveKit track SIDs. The current environment exposes an ALSA capture
device and several playback devices through `/dev/snd`, but the locked `sounddevice` import fails
because PortAudio is unavailable and no terminal RTC client exists. Device enumeration alone is
not a microphone/playback smoke, and no command in this runbook is presented as a passed room-audio
test.

## Offline acceptance smoke and quality gates

The aggregate smoke runs the two-stage fake lifecycle plus real temporary SQLite scoring,
recovery/retention, and localhost HTTP results workflows. It removes provider keys from child
processes and reports `live_audio_verified: false` by design:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run python scripts/p10_offline_acceptance_smoke.py
```

Run the complete offline quality suite:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run ruff format --check .
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run ruff check .
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run mypy src
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run pytest
```

## Recovery, restart, cleanup, and shutdown

SQLite score tasks survive worker exit and use expiring leases. Restart a stopped worker with the
same command; succeeded tasks are not redelivered. The offline recovery contract preserves the
last committed evidence, remaining active time, interrupted-question reference, and recording
segment, with one shared 120-second recovery deadline. Automatic checkpoint emission and real
participant/track rebinding are not yet wired into a production controller.

Run `interview cleanup` at startup and at least daily. The tested user-level systemd timer setup,
failure behavior, and exact 30-day UTC boundary are documented in `docs/retention.md`. Failed file
deletions remain retryable, and interviews prepared for deletion are immediately hidden from the
viewer.

For orderly shutdown, stop candidate and Agent Server processes first when those entrypoints
exist, allow the worker to finish its current assessment, then stop the worker, results viewer,
and local LiveKit Server with `Ctrl-C`. Do not delete the SQLite database or recording directory
as a shutdown procedure.

## Troubleshooting

- `Missing required setting`: export the named value in the same shell that starts the command.
- `HR_VOICE_ID and TECH_VOICE_ID must be distinct`: configure two different accessible voices.
- No audio devices: run outside the restricted environment, confirm `/dev/snd`, PipeWire/ALSA,
  and PortAudio access, then repeat device listing. Do not substitute synthetic audio for the gate.
- Results page is empty: confirm `SQLITE_PATH` points to the database populated by the interview
  workflow and that the record is not expired or pending deletion.
- Worker finds no task: `score_task=none` is expected for `--once` when the queue is empty.
- SQLite lock/transient failure: stop duplicate operator processes, keep transactions short, and
  retry; the database config enables WAL and a busy timeout.
- Provider authentication/model/voice failure: correct the local account configuration. Do not
  silently switch model, STT/TTS provider, or voice.
- Live production interview command missing: this is a known implementation blocker, not an
  installation problem. See `docs/ACCEPTANCE.md` and `PROGRESS.md`.
