# Local Interview Application User Guide

This guide explains how to configure, validate, start, use, test, and stop the parts of the
application that are currently implemented. Run every command from the repository root.

> [!IMPORTANT]
> The local LiveKit server, operator console, scoring worker, results viewer, cleanup workflow, and
> offline two-stage simulation, ROOM Agent Server, and terminal RTC candidate are runnable. A
> physical interview still requires working PortAudio microphone/speaker devices and verified
> provider account access; those live gates have not passed on this host.

## 1. Requirements

The verified development environment uses:

- Ubuntu 26.04 x86_64
- CPython 3.14
- uv 0.12.17
- LiveKit Server 1.13.7
- LiveKit CLI 2.18.2
- LiveKit Agents and provider plugins 1.8.2

This checkout keeps the verified executables under `.tools/bin/`. Confirm that they are present:

```bash
.tools/bin/uv --version
.tools/bin/livekit-server --version
.tools/bin/lk --version
```

Install the locked Python environment:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv sync --frozen --group dev
```

## 2. Configure `.env`

The CLI automatically reads `.env` from the current working directory. You do not need to run
`source .env`. Environment variables explicitly exported in the shell override `.env` values.

If `.env` does not exist, create it and restrict access:

```bash
cp .env.example .env
chmod 600 .env
```

Use this structure:

```dotenv
# Local LiveKit development server. Never use these credentials outside localhost.
LIVEKIT_URL=ws://127.0.0.1:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret

# OpenRouter
OPENROUTER_API_KEY=YOUR_OPENROUTER_KEY
OPENROUTER_MODEL=anthropic/claude-sonnet-5

# ElevenLabs
ELEVEN_API_KEY=YOUR_ELEVENLABS_KEY
ELEVEN_STT_MODEL=scribe_v2_realtime
ELEVEN_TTS_MODEL=eleven_turbo_v2_5
HR_VOICE_ID=21m00Tcm4TlvDq8ikWAM
TECH_VOICE_ID=ErXwobaYiN019PkySvjV

# Fixed interview policy
INTERVIEW_LANGUAGE=en
HR_TARGET_SECONDS=300
TECH_TARGET_SECONDS=300
IDLE_CHECKIN_SECONDS=5
THINKING_HOLD_SECONDS=20

# Local storage and services
SQLITE_PATH=data/interviews.sqlite3
RECORDINGS_DIR=data/recordings
RESULTS_HOST=127.0.0.1
RESULTS_PORT=8080
CONTROL_HOST=127.0.0.1
CONTROL_PORT=8090
INTERVIEW_AGENT_NAME=interview-agent
SCORING_WORKER_ID=local-scoring-worker
SCORING_POLL_SECONDS=2
```

Replace only the OpenRouter and ElevenLabs API-key placeholders. The configured voice IDs are
distinct premade voices: Rachel for HR and Antoni for Technical. Voice availability and model
access depend on the associated provider accounts.

Do not commit `.env`, print its contents, or paste it into issue reports.

## 3. Validate configuration

Validate all settings without printing secrets:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview config-check
```

Expected output:

```text
configuration=valid
source=.env+process-environment
secrets=redacted
```

Validation checks required credentials, distinct voice IDs, fixed language and timing values,
local-only results binding, paths, port, and worker polling configuration. It does not make a
provider request.

## 4. Start the available services

Use separate terminals and keep each long-running command open.

### Terminal 1 — LiveKit server

```bash
cd /home/bashmohandes-abdallah/Nancy-ai/LiveKit_CLI
.tools/bin/livekit-server --dev --bind 127.0.0.1
```

The development server listens at `ws://127.0.0.1:7880`. The `devkey`/`secret` pair is deliberately
insecure and suitable only for local development.

### Terminal 2 — ROOM Agent Server

```bash
cd /home/bashmohandes-abdallah/Nancy-ai/LiveKit_CLI
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview-agent dev --no-reload
```

Keep this process running before creating a mission so it can claim `interview-agent` dispatches.

### Terminal 3 — scoring worker

```bash
cd /home/bashmohandes-abdallah/Nancy-ai/LiveKit_CLI
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview worker
```

The worker polls the SQLite score-task queue and sends queued immutable transcript snapshots to
the configured OpenRouter model. Stop it with `Ctrl+C`. To poll once and exit:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview worker --once
```

`score_task=none` means the queue is empty; it is not an error.

### Terminal 4 — operator console

```bash
cd /home/bashmohandes-abdallah/Nancy-ai/LiveKit_CLI
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview control
```

Open `http://127.0.0.1:8090/interviews/new`, enter the candidate name, and choose **Start
interview**. This creates a unique local room and dispatches `interview-agent`. The status page
shows room, dispatch, agent-job, and candidate-participant readiness.

### Terminal 5 — terminal candidate

List devices, then either create-and-join directly or join the ID shown by the operator console:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview devices
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview run --name "Candidate Name"
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview join --interview-id INTERVIEW_ID
```

Use `--input-device` and `--output-device` when necessary. The candidate command publishes the
microphone and plays agent audio; the browser remains an operator-only surface.

### Terminal 6 — results viewer

```bash
cd /home/bashmohandes-abdallah/Nancy-ai/LiveKit_CLI
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview results
```

Open:

```text
http://127.0.0.1:8080/results
```

The viewer is read-only and localhost-only. An empty page means the configured database contains
no visible, non-expired interview results.

## 5. Exercise the two-stage lifecycle

Run the provider-free simulation:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview dry-run --name "Candidate Name"
```

Expected stage order:

```text
event=hr:started
event=hr:draining
event=hr:closed
event=technical:started
event=technical:draining
event=technical:closed
```

This validates application orchestration only. It does not create a LiveKit room, contact a
provider, write an interview to SQLite, or capture audio.

## 6. Run verification

Run the offline acceptance workflow:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run python scripts/p10_offline_acceptance_smoke.py
```

It should report `"status": "passed"`, `"provider_request_made": false`, and
`"live_audio_verified": false`.

Run all quality gates:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run ruff format --check .
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run ruff check .
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run mypy src
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run pytest
```

The current verified baseline is 44 passing tests. On a restricted sandbox, SQLite asynchronous
tests may stall; run them from a normal local terminal.

Optional real-room signaling probes, with the local LiveKit server already running:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run python scripts/p00_session_lifecycle_probe.py
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run python scripts/p03_livekit_handoff_probe.py
```

These prove same-room session lifecycle and handoff without microphone or speaker media. They are
not live-audio tests.

## 7. Retention cleanup

Cleanup permanently removes interviews and owned artifacts that have reached the fixed 30-day
retention boundary. Review the configured `SQLITE_PATH` and `RECORDINGS_DIR` before running it:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview cleanup
```

Do not run cleanup as a harmless startup test against data you intend to keep. Scheduling details
are in [retention.md](retention.md).

## 8. Stop the services

Press `Ctrl+C` in this order:

1. Terminal candidate.
2. ROOM Agent Server.
3. Scoring worker, after allowing an active assessment to finish.
4. Operator console and results viewer.
5. Local LiveKit server.

Do not delete `data/interviews.sqlite3` or `data/recordings/` as a shutdown step.

## 9. Troubleshooting

- **Missing required setting:** Fill the named `.env` value and rerun `interview config-check`.
- **Voice IDs must be distinct:** Use different ElevenLabs voice IDs for HR and Technical.
- **Provider authentication/model error:** Verify account access and billing. Do not silently
  switch the required model or provider.
- **Results page is empty:** Confirm `SQLITE_PATH`, then check whether the database has results that
  are neither expired nor pending deletion.
- **Port 7880 or 8080 is already in use:** Stop the previous local process before restarting it.
- **No microphone or speaker:** Confirm `/dev/snd`, PipeWire/ALSA, and PortAudio from a normal host
  session, then rerun `interview devices`.

## 10. Current usage boundary

The planned two-session voice path is implemented, but it is not yet fully accepted. Microphone,
STT, and opening LLM generation have passed live; ElevenLabs TTS is blocked by HTTP 402. Remaining
work also includes observable production recording, automatic live recovery/rebinding, durable
case and hint evidence, and the live acceptance tests described in `PROGRESS.md`.
