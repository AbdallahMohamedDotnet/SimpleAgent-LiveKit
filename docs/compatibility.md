# Local compatibility report

Checked on 20 September 2026. Commands were executed from the repository root. Live provider,
voice, and physical audio checks remain blocked; verified local control-plane and SDK lifecycle
results are reported separately from those gates.

## Status summary

| Capability | Status | Evidence |
|---|---|---|
| Ubuntu, architecture, Python, and uv | PASS | Ubuntu 26.04.1 LTS x86_64; CPython 3.14.4; uv 0.12.17 |
| LiveKit CLI and local server install | PASS | Checksum-verified `lk` 2.18.2 and `livekit-server` 1.13.7 in ignored `.tools/bin/` |
| Local server and CLI project | PASS | Server bound to `127.0.0.1:7880`; CLI project `local-dev` configured with development credentials |
| Real room and participant control path | PASS | Room `RM_KxWxgvbH4Nxd`; `p00-terminal (ACTIVE)`, one participant, zero tracks |
| Two sequential AgentSession lifecycles | PASS (media disabled) | HR and technical sessions closed while room SID and RTC participant SID remained unchanged |
| Provider adapter construction | PASS (offline only) | Pinned 1.8.2 OpenRouter/ElevenLabs objects construct with required model, realtime STT, English, and distinct configured TTS instances; no request was sent |
| Terminal microphone and speaker in room | BLOCKED | `lk room join` has no device flags; no accessible audio device exists in this execution environment |
| Sonnet 5 through OpenRouter | BLOCKED | `OPENROUTER_API_KEY` is unset; account/model/streaming/tool/structured-output behavior is unverified |
| ElevenLabs streaming STT/TTS and two voices | BLOCKED | API key and both voice IDs are unset; account, model, and voice access are unverified |
| Published audio capture/interruption/alignment | BLOCKED | No accessible input/output device or provider-backed session; no media tracks were published |

The room evidence is not presented as an audio pass. The acceptance gate still requires an
operator-confirmed microphone/speaker test with published track events.

## Selected local toolchain

- OS: Ubuntu 26.04.1 LTS (resolute), Linux kernel 7.0.0-31-generic.
- Architecture: x86_64.
- System and selected project Python: CPython 3.14.4 (`>=3.14,<3.15`).
- uv: 0.12.17 in `.tools/bin/`.
- LiveKit CLI: 2.18.2 in `.tools/bin/lk`.
- LiveKit Server: 1.13.7 in `.tools/bin/livekit-server`.
- Isolated Python compatibility probe: `livekit-agents`, `livekit-plugins-elevenlabs`, and
  `livekit-plugins-openai` 1.8.2 imported successfully on CPython 3.14.4. P01 subsequently pinned
  all three in `pyproject.toml` and `uv.lock`; P04 added offline provider-construction coverage.
- Other detected tools: Go 1.26.0, Docker CLI 29.8.0, PipeWire 1.6.2, WirePlumber 0.5.13,
  ALSA utilities 1.2.15.2, and FFmpeg 8.0.1. The Docker daemon socket is not accessible to this
  execution environment and was not needed for the verified binary workflow.

The official release archives and `checksums.txt` files were downloaded from the respective
GitHub releases. Both Linux amd64 archives passed `sha256sum --check --strict` before their
binaries were installed locally. No global or privileged package installation was performed.

## Verified LiveKit CLI syntax

The following is the installed 2.18.2 syntax, not proposed or copied from an older template:

```text
lk project add PROJECT_NAME --url URL --api-key KEY --api-secret SECRET --default
lk project set-default PROJECT_NAME
lk room create [--empty-timeout SECS] ROOM_NAME
lk room list [--json] [ROOM_NAME ...]
lk room participants list ROOM_NAME
lk room join [--identity ID] [--auto-subscribe] ROOM_NAME
lk dispatch create --room ROOM --agent-name AGENT [--metadata JSON]
lk dispatch list ROOM_NAME
lk agent dev [options] [entrypoint] [-- python-args...]
lk agent start [options] [entrypoint] [-- python-args...]
lk agent console [--input-device DEVICE] [--output-device DEVICE] [--list-devices] [entrypoint]
```

`lk agent` is described by this release as managing LiveKit Cloud Agents, but its `dev`, `start`,
and `console` commands accept the same global local-server URL/key options. Cloud create/deploy
commands are outside this project's scope and were not used.

`lk room join` can publish encoded files, sockets, or demo media and can auto-subscribe, but it has
no microphone or speaker device flags. `lk agent console` exposes device flags, but console mode
is not evidence of a candidate participating in the required real room. Therefore the planned
fallback remains a small Python RTC terminal participant when host audio becomes accessible.

## Local server, room, and participant evidence

The local server was started with:

```text
.tools/bin/livekit-server --dev --bind 127.0.0.1
```

It reported HTTP/signaling port 7880, RTC TCP port 7881, RTC UDP port 7882, single-node routing,
node ID `ND_n64HWefr9L5b`, and version 1.13.7. The standard local development key pair was stored
by `lk project add` in the CLI's user configuration as project `local-dev`; no cloud project was
created.

Room `p00-compatibility` was created through the RoomService API. The second reproducible run
reported room SID `RM_KxWxgvbH4Nxd`. A separate long-running CLI process joined with identity
`p00-terminal`; `lk room participants list` reported it as `ACTIVE`, and `lk room list --json`
reported one participant. It had zero tracks, so this proves signaling/participant connection,
not audio publication.

## Audio backend findings

- PipeWire and WirePlumber packages are installed, but `pw-cli info 0` failed to connect with
  `Operation not permitted` in this execution environment.
- `/dev/snd` is absent. `arecord -l` and `aplay -l` both report no sound cards. The current user is
  not a member of the `audio` group.
- `lk agent console --list-devices` returned no devices. The precompiled binary first looked for
  an ALSA configuration under its build-runner path. Pointing `ALSA_CONFIG_PATH` at the host
  configuration still found no PCM devices and caused a PortAudio initialization crash. This is
  a CLI/device-path compatibility issue to recheck in a normal host terminal; it is not treated
  as proof that the physical machine lacks hardware.

Required follow-up: run the terminal RTC participant from a host session that can access PipeWire
or ALSA, publish microphone audio in `p00-compatibility`, observe the audio track from another
participant/recorder, play agent audio, and record an operator confirmation. Capture track SIDs
and events without storing candidate content in operational logs.

## Python SDK and two-session lifecycle evidence

The isolated compatibility environment used LiveKit Agents 1.8.2. Runtime signature inspection
confirmed:

- `AgentSession.shutdown(drain=True)` schedules graceful close and draining.
- `await AgentSession.aclose()` waits for immediate session cleanup.
- `RoomOptions` supports participant identity, `close_on_disconnect`, and
  `delete_room_on_close=False`.
- `RoomIO.start()` and `RoomIO.aclose()` are separate lifecycle methods.

[`scripts/p00_session_lifecycle_probe.py`](../scripts/p00_session_lifecycle_probe.py) connected one
`rtc.Room`, started and closed distinct HR and technical `AgentSession` instances with all media
and model activity disabled, then disconnected the room explicitly. After each session close:

- the room remained connected;
- room SID `RM_KxWxgvbH4Nxd` was unchanged; and
- local RTC participant SID `PA_b2tNJCtZcrEg` was unchanged.

This verifies the basic ownership strategy: the job/controller owns the `rtc.Room`, while each
session owns and closes its own RoomIO. It does not yet prove draining real TTS, final STT commits,
audio ownership release, or absence of overlap with live tracks. P03 must repeat the handoff with
actual media and providers before claiming the full lifecycle gate.

Probe command:

```text
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv run --isolated --python 3.14 \
  --with 'livekit-agents==1.8.2' python scripts/p00_session_lifecycle_probe.py
```

The local development secret is intentionally short and triggered a JWT library warning. It is
the server's documented development-only credential, not suitable for a non-local deployment.

## Provider/plugin findings and blocked live checks

The direct LiveKit plugins import on Python 3.14.4. Version 1.8.2 exposes ElevenLabs streaming STT
configuration including model selection, realtime mode, sample rate, server VAD, timestamps, and
keyterms. Its TTS adapter accepts explicit `voice_id` and model; its default model is
`eleven_turbo_v2_5`. The OpenAI-compatible LLM adapter accepts an explicit `model`, `api_key`,
`base_url`, tool choice, parallel tool calls, retries, and extra request fields, which is the
intended OpenRouter boundary.

These imports and signatures are compatibility evidence only. The following variables were
checked for presence without printing values and were unset: `OPENROUTER_API_KEY`,
`ELEVEN_API_KEY`, `HR_VOICE_ID`, and `TECH_VOICE_ID`. Consequently none of the following is
verified: Sonnet 5 account access, exact supported request parameters, streaming, tool calls,
structured scoring responses, ElevenLabs streaming STT/TTS, or access to two distinct voices. No
fallback model, inference service, or voice was substituted.

## Recording, interruption, and timestamp limits

No actual audio track was published, so recording and delivery claims remain blocked. Generated
TTS bytes alone will not be treated as proof that speech was played. A later media probe must
distinguish captured published frames, playback/track events, interruptions, canceled output, and
what remote audibility cannot prove. Timestamp alignment must be measured against room/media
events and persisted with explicit uncertainty.

## Sources

- [LiveKit CLI repository and install guidance](https://github.com/livekit/livekit-cli)
- [LiveKit CLI 2.18.2 release](https://github.com/livekit/livekit-cli/releases/tag/v2.18.2)
- [LiveKit Server repository and local startup](https://github.com/livekit/livekit)
- [LiveKit Server 1.13.7 release](https://github.com/livekit/livekit/releases/tag/v1.13.7)
- [Running LiveKit locally](https://docs.livekit.io/transport/self-hosting/local/)
- [AgentSession and RoomIO lifecycle](https://docs.livekit.io/agents/logic/sessions/)
- [Job/session shutdown behavior](https://docs.livekit.io/agents/server/job/)

## Remaining P00 gate

P00 remains `IN_PROGRESS / BLOCKED`. To finish it, provide a host execution session with usable
microphone and speaker access plus locally injected OpenRouter and ElevenLabs credentials and two
different ElevenLabs voice IDs. Then run the real-room audio, provider, voice, drain, interruption,
capture, and timestamp checks. Missing live inputs are recorded as blockers, not converted into
synthetic passes.

The latest strict-order recheck found `OPENROUTER_API_KEY`, `ELEVEN_API_KEY`, `HR_VOICE_ID`,
`TECH_VOICE_ID`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` unset in the execution shell.
`/dev/snd` remained absent and `lk agent console --list-devices` returned no devices. Although
`sounddevice` 0.5.6 is present through the locked dependency graph, importing it fails with
`OSError: PortAudio library not found`. Installing PortAudio would still not provide devices while
the host audio interface is unavailable.
