# Local compatibility report

Initially checked on 20 September 2026 and reconciled with live evidence on 21 September 2026.
Commands were executed from the repository root. Microphone publication, ElevenLabs STT, and an
OpenRouter response are live-verified; ElevenLabs TTS and speaker playback remain blocked.

## Status summary

| Capability | Status | Evidence |
|---|---|---|
| Ubuntu, architecture, Python, and uv | PASS | Ubuntu 26.04.1 LTS x86_64; CPython 3.14.4; uv 0.12.17 |
| LiveKit CLI and local server install | PASS | Checksum-verified `lk` 2.18.2 and `livekit-server` 1.13.7 in ignored `.tools/bin/` |
| Local server and CLI project | PASS | Server bound to `127.0.0.1:7880`; CLI project `local-dev` configured with development credentials |
| Real room and participant control path | PASS | Room `RM_KxWxgvbH4Nxd`; `p00-terminal (ACTIVE)`, one participant, zero tracks |
| Two sequential AgentSession lifecycles | PASS (media disabled) | HR and technical sessions closed while room SID and RTC participant SID remained unchanged |
| Provider adapter construction | PASS | Pinned 1.8.2 OpenRouter/ElevenLabs objects construct with the fixed model, realtime STT, English, and distinct configured TTS voices |
| Terminal microphone in room | PASS | A project-local PortAudio runtime enumerated host devices and the terminal client published an unmuted microphone track |
| Sonnet 5 through OpenRouter | PARTIAL | The configured model generated and persisted the opening HR question; scoring/tool/structured-output tasks remain unverified live |
| ElevenLabs streaming STT/TTS and two voices | PARTIAL | STT commits final transcripts with server-side VAD; both voices stream TTS audio. The earlier 402 was a library HR voice, now replaced. In-room playback unverified |
| Published audio capture/interruption/alignment | BLOCKED | Candidate input publication passed, but agent output, speaker playback, recording alignment, and interruption remain unverified |

The microphone evidence is not presented as a two-way audio pass. The acceptance gate still
requires generated agent audio, speaker playback, both voices, and complete stage handoff.

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

The later production terminal participant used a project-local PortAudio runtime to enumerate the
host PipeWire/ALSA devices and publish an unmuted microphone track. Required follow-up is now to
enable ElevenLabs TTS, play agent audio, capture both directions through the recorder, and record
operator confirmation without storing candidate content in operational logs.

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

The ignored local configuration was later populated without printing secret values. A live room
exercise verified ElevenLabs realtime STT and OpenRouter generation with the fixed model. A direct
two-word ElevenLabs TTS probe returned non-retryable HTTP 402 `Payment Required`; no fallback
model, inference service, provider, or voice was substituted. Structured scoring, tool behavior,
both-voice playback, and full streaming output remain unverified.

Update, 21 September 2026. The 402 body was `paid_plan_required`: "Free users cannot use library
voices via the API." It applied only to the HR voice `21m00Tcm4TlvDq8ikWAM`; the technical voice
returned audio. With the operator's approval the HR voice was changed to the default voice Sarah
(`EXAVITQu4vr4xnSDxMaL`), which the account can use; provider and model are unchanged. The API key
lacks `user_read` and `voices_read`, so account tier and the voice list cannot be queried with it.
Separately, realtime STT used `commit_strategy=manual`, and no session ran a local VAD to send
commits, so only partial transcripts arrived. The STT adapter now enables ElevenLabs server-side
VAD with a 2-second silence threshold; a live probe then returned a final transcript and
end-of-speech. Both voices streamed audio through the production TTS objects.

## Recording, interruption, and timestamp limits

A candidate microphone track was published, but the recording sink is not wired to observable
room media. On 23 September 2026 the terminal participant added WebRTC acoustic echo cancellation:
remote speaker frames are supplied as the 10 ms reverse stream and microphone frames are filtered
before publication, using the PortAudio input/output latency estimate. The native processor and
adapter wiring pass offline tests, but the reported self-interruption loop and genuine live
barge-in still require an audible room retest. A later media probe must distinguish captured input,
generated output, playback/track events, interruptions, canceled output, and what remote
audibility cannot prove. Timestamp alignment must be measured against room/media events and
persisted with explicit uncertainty.

## Sources

- [LiveKit CLI repository and install guidance](https://github.com/livekit/livekit-cli)
- [LiveKit CLI 2.18.2 release](https://github.com/livekit/livekit-cli/releases/tag/v2.18.2)
- [LiveKit Server repository and local startup](https://github.com/livekit/livekit)
- [LiveKit Server 1.13.7 release](https://github.com/livekit/livekit/releases/tag/v1.13.7)
- [Running LiveKit locally](https://docs.livekit.io/transport/self-hosting/local/)
- [AgentSession and RoomIO lifecycle](https://docs.livekit.io/agents/logic/sessions/)
- [Job/session shutdown behavior](https://docs.livekit.io/agents/server/job/)

## Remaining P00 gate

P00 remains `IN_PROGRESS`. The provider-level STT/TTS blocker is resolved (see the 21 September
2026 update above). To finish it, run real-room TTS playback, both distinct voices, drain,
interruption, capture, and timestamp checks. Provider-level probes are not a substitute for that
in-room evidence.
