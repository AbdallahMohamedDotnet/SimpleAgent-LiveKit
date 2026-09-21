# Ubuntu operator runbook

This runbook describes the commands that have actually been exercised in this checkout. The
ROOM Agent Server, terminal RTC client, and full durable two-stage path are implemented. A
project-local PortAudio runtime has verified microphone capture through PipeWire, ElevenLabs STT,
and OpenRouter generation. The current live gate is ElevenLabs TTS billing: the configured account
returns HTTP 402 `Payment Required`, so audible speaker playback is not yet verified.

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

The CLI automatically reads `.env` from the directory in which it is started. Real process
environment variables take precedence over values in that file. The checked-out `.env` is ignored
by Git and restricted to the current user; never commit it or paste its secrets into logs.

If `.env` is missing on another checkout, create it from the template:

```bash
cp .env.example .env
chmod 600 .env
```

For the local `livekit-server --dev` process, keep `LIVEKIT_URL=ws://127.0.0.1:7880`,
`LIVEKIT_API_KEY=devkey`, and `LIVEKIT_API_SECRET=secret`. These credentials are deliberately
insecure and must never be used on a network-accessible server. Add an OpenRouter key with access
to `anthropic/claude-sonnet-5`, an ElevenLabs key, and two different accessible ElevenLabs voice
IDs. The fixed language and timing values must remain unchanged. Runtime data defaults to
`data/interviews.sqlite3` and `data/recordings/`.

Validate all settings without printing secrets:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview config-check
```

It prints `configuration=valid` only when the complete configuration is usable. You do not need
to run `source .env`.

## Start the currently implemented services

Run every command below from the repository root. First install the locked environment and check
configuration:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv sync --frozen --group dev
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview config-check
```

Terminal 1 — start the local LiveKit server:

```bash
.tools/bin/livekit-server --dev --bind 127.0.0.1
```

Terminal 2 — start the local ROOM Agent Server:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview-agent dev --no-reload
```

Terminal 3 — run retention cleanup once, then start the scoring worker:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview cleanup
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview worker
```

Terminal 4 — start the operator console:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview control
```

Open `http://127.0.0.1:8090/interviews/`. Enter the candidate name to create a real local
LiveKit room, persist generated identities, and send an explicit dispatch to `interview-agent`.
The status page reports whether the matching agent job and exact candidate participant have
joined. It also shows finalized HR and technical transcript turns and refreshes every two seconds.
Its microphone icon reflects whether the terminal audio client is connected, and the page shows
the exact terminal join command for that interview. It does not capture browser audio; microphone
and speaker ownership remain in the terminal client.

Terminal 5 — start the results viewer:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview results
```

Open `http://127.0.0.1:8080/results`. Both web services are fixed to `127.0.0.1`; neither is a
candidate interview UI. Use `interview worker --once` for one queue poll instead of a continuous
worker. A real provider call has not yet been verified, so observe its first result before relying
on it.

Terminal 6 — list devices, then create and join the interview from the terminal:

```bash
LD_LIBRARY_PATH="$PWD/.tools/portaudio/usr/lib/x86_64-linux-gnu" \
  UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview devices
LD_LIBRARY_PATH="$PWD/.tools/portaudio/usr/lib/x86_64-linux-gnu" \
  UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview run --name "Candidate Name"
```

Use `--input-device` and `--output-device` with a device name or numeric index when the system
defaults are unsuitable. To join a mission already created by the operator console, run
`interview join --interview-id ID`. Stop the terminal participant with `Ctrl-C`.

Terminal 7 — run the available provider-free lifecycle check:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview dry-run --name "Candidate Name"
```

It creates generated internal IDs and exercises two distinct fake stage runtimes. It creates no
room, audio, SQLite record, or provider request.

### One-command start

`scripts/run_local.sh` performs the steps above in order: config check, LiveKit dev server
(reused if already listening), ROOM Agent Server, retention cleanup, scoring worker, results
viewer, operator console, and a
media-disabled local room with the two sequential HR/technical `AgentSession` stages. It logs to
`data/logs/`, refuses a busy results port, and stops only the processes it started on `Ctrl-C`.
Useful flags include `--skip-cleanup`, `--no-agent`, `--no-probe`, `--no-control`,
`--dry-run "Name"`, `--once`, and `--help`. Cleanup
permanently deletes interviews past the 30-day retention, so use `--skip-cleanup` when unsure.

## Remaining live voice blockers

The terminal client has published real 48 kHz mono microphone PCM, ElevenLabs realtime STT has
transcribed it, and OpenRouter has generated an HR question. ElevenLabs returned HTTP 402 for TTS,
so no agent audio was generated for the speaker. Enable billing/credits on the configured
ElevenLabs account, then repeat the live smoke before treating speaker output, voice handoff, or a
complete interview as passed.

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

From a normal host session with PipeWire or ALSA access, list application devices:

```bash
LD_LIBRARY_PATH="$PWD/.tools/portaudio/usr/lib/x86_64-linux-gnu" \
  UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview devices
```

The terminal client exposes explicit input/output selection, publishes a microphone track, and
plays subscribed agent tracks. This checkout contains an ignored, project-local extracted
PortAudio runtime under `.tools/portaudio`; the `LD_LIBRARY_PATH` prefix above is required unless
the system package is installed. Microphone capture is verified, but playback remains blocked by
the upstream TTS billing response.

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

- `Missing required setting`: fill the named value in `.env`, or export it in the starting shell
  to override `.env`, then rerun `interview config-check`.
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
- `PortAudio is unavailable`: install the host PortAudio runtime, confirm the microphone/speaker
  are visible with `interview devices`, and rerun the terminal candidate command.
