# Local Interview Application User Guide

This guide explains how to configure, validate, start, use, test, and stop the parts of the
application that are currently implemented. Run every command from the repository root.

> [!IMPORTANT]
> Everything in this application runs in a terminal. There is no web page and no local HTTP
> service to open. The local LiveKit server, ROOM Agent Server, scoring worker, terminal RTC
> candidate, status and results commands, cleanup workflow, and the offline two-stage simulation
> are runnable. A physical interview still requires working PortAudio microphone/speaker devices
> and verified provider account access; those live gates have not passed on this host.

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
HR_VOICE_ID=EXAVITQu4vr4xnSDxMaL
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
INTERVIEW_AGENT_NAME=interview-agent
SCORING_WORKER_ID=local-scoring-worker
SCORING_POLL_SECONDS=2
```

Replace only the OpenRouter and ElevenLabs API-key placeholders. The configured voice IDs are
distinct default voices: Sarah for HR and Antoni for Technical. Free ElevenLabs accounts cannot
use Voice Library voices through the API (HTTP 402 `paid_plan_required`), so choose default or
your own voices on a free plan.

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
local data paths, the agent dispatch name, and worker polling configuration. It does not make a
provider request.

## 4. Easiest way: the operator menu

```bash
./run.sh
```

This is the single entry point. It prepares the environment and opens a numbered menu:

```text
  1) Start background services (LiveKit, agent server, scoring worker)
  2) Stop background services
  3) Start a new interview (uses this terminal's microphone)
  4) Rejoin an existing interview
  5) Show live interview status
  6) List retained interview results
  7) Show one interview's full results
  8) Locate a recording file
  9) List audio devices
 10) Check configuration
 11) Run retention cleanup (deletes data past 30 days)
 12) Offline dry run (no providers, no room, no audio)
  0) Quit
```

A normal session is: `1` (wait for `livekit=reachable`), then `3`, answer the candidate name,
talk, `Ctrl-C` to leave the interview, then `6`/`7` to read the results. Quitting with `0` stops
the services the menu started. Options that need an interview or a recording show a numbered pick
list, so you never have to copy an ID by hand.

The sections below describe the same functions as individual commands, for scripting or when you
prefer one process per terminal.

## 5. Start the available services manually

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

### Terminal 4 — terminal candidate

List devices, then create and join the interview, or rejoin an existing one:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview devices
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview run --name "Candidate Name"
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview join --interview-id INTERVIEW_ID
```

`interview run` creates a unique local room, dispatches `interview-agent`, prints the generated
`interview_id`, and connects terminal audio. Use `--input-device` and `--output-device` when
necessary. This command owns the microphone and speaker.

<<<<<<< HEAD
While you are in the room the terminal prints the conversation as it happens, one line per
spoken turn (`[Interviewer] ...` and `[You] ...`); rejoining first replays the transcript so far.

`interview join` only works while the interviewer is still running in the room. An interview that
is `incomplete` or finished, or whose room no longer exists (a restarted LiveKit dev server
forgets every room), is refused with an explanation, because no agent would answer. Start a new
interview instead.

=======
>>>>>>> origin/main
### Terminal 5 — status and results

```bash
cd /home/bashmohandes-abdallah/Nancy-ai/LiveKit_CLI
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview status --interview-id INTERVIEW_ID
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview results list
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview results show --interview-id INTERVIEW_ID
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview results recording --segment-id SEGMENT_ID
```

`status` shows room, dispatch, agent-job and candidate-participant readiness plus the finalized
transcript. `results list` shows every retained interview with its HR and technical score and
coverage; `retained_interviews=0` means the configured database holds no visible, non-expired
result. `results show` prints the two stage assessments separately, with per-competency rationale,
cited evidence turns, transcripts and recording status. `results recording` prints the local file
path of one segment; open it with any audio player.

These commands only read. They exit `0` on success, `2` for a usage error, and `3` when the
requested ID is unknown, expired or unavailable. Add `--json` to any of them for scripting.
Candidate and model text is escaped before printing, so control characters appear as `\x1b`-style
escapes instead of affecting your terminal.

## 6. Exercise the two-stage lifecycle

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

## 7. Run verification

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

The current verified baseline is 59 passing tests. On a restricted sandbox, SQLite asynchronous
tests may stall; run them from a normal local terminal.

Optional real-room signaling probes, with the local LiveKit server already running:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run python scripts/p00_session_lifecycle_probe.py
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run python scripts/p03_livekit_handoff_probe.py
```

These prove same-room session lifecycle and handoff without microphone or speaker media. They are
not live-audio tests.

## 8. Retention cleanup

Cleanup permanently removes interviews and owned artifacts that have reached the fixed 30-day
retention boundary. Review the configured `SQLITE_PATH` and `RECORDINGS_DIR` before running it:

```bash
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run interview cleanup
```

Do not run cleanup as a harmless startup test against data you intend to keep. Scheduling details
are in [retention.md](retention.md).

## 9. Stop the services

Press `Ctrl+C` in this order:

1. Terminal candidate.
2. ROOM Agent Server.
3. Scoring worker, after allowing an active assessment to finish.
4. Local LiveKit server.

The status and results commands exit on their own and need no shutdown step.

Do not delete `data/interviews.sqlite3` or `data/recordings/` as a shutdown step.

## 10. Troubleshooting

- **Missing required setting:** Fill the named `.env` value and rerun `interview config-check`.
- **Voice IDs must be distinct:** Use different ElevenLabs voice IDs for HR and Technical.
- **Provider authentication/model error:** Verify account access and billing. Do not silently
  switch the required model or provider.
- **`results list` prints `retained_interviews=0`:** Confirm `SQLITE_PATH`, then check whether the
  database has results that are neither expired nor pending deletion.
- **A results command exits `3`:** The ID is unknown, past its 30-day retention, pending deletion,
  or its recording file is missing from `RECORDINGS_DIR`.
- **Port 7880 is already in use:** Stop the previous local LiveKit server before restarting it.
- **No microphone or speaker:** Confirm `/dev/snd`, PipeWire/ALSA, and PortAudio from a normal host
  session, then rerun `interview devices`.

## 11. Current usage boundary

The planned two-session voice path is implemented, but it is not yet fully accepted. Microphone,
STT, opening LLM generation, and TTS for both voices have passed at the provider level; an
audible in-room interview has not been verified yet. Remaining
work also includes observable production recording, automatic live recovery/rebinding, durable
case and hint evidence, and the live acceptance tests described in `PROGRESS.md`.
