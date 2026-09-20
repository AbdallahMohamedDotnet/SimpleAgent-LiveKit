# Source references and verification policy

These references informed the specification and compatibility work on 20 September 2026. Local
checks subsequently verified LiveKit CLI 2.18.2, LiveKit Server 1.13.7, CPython 3.14.4, and
LiveKit Agents/ElevenLabs/OpenAI-compatible plugins 1.8.2. Provider account capabilities and
physical audio remain unverified; see `docs/compatibility.md` for the evidence boundary.

| Source | Relevant fact / check |
|---|---|
| [LiveKit CLI](https://docs.livekit.io/reference/developer-tools/livekit-cli/) | Local project management and Python template scaffolding; inspect installed help for current syntax |
| [LiveKit CLI repository](https://github.com/livekit/livekit-cli) | Source/release behavior and available terminal audio features |
| [Local LiveKit Server](https://docs.livekit.io/transport/self-hosting/local/) | Local server startup and binding |
| [Agent startup modes](https://docs.livekit.io/agents/server/startup-modes/) | Console can run without connecting to LiveKit; dev/start and connected-room testing are separate |
| [AgentSession and RoomIO](https://docs.livekit.io/agents/logic/sessions/) | Session lifecycle, participant binding, cleanup/disconnect options |
| [OpenRouter plugin](https://docs.livekit.io/agents/models/llm/openrouter/) | OpenRouter integration through the OpenAI-compatible LiveKit plugin |
| [ElevenLabs STT plugin](https://docs.livekit.io/agents/models/stt/elevenlabs/) | Direct plugin and streaming STT configuration |
| [ElevenLabs TTS plugin](https://docs.livekit.io/agents/models/tts/elevenlabs/) | Voice/model configuration and direct credentials |
| [Sonnet 5 migration guide](https://openrouter.ai/docs/cookbook/evaluate-and-optimize/model-migrations/sonnet-5) | Model ID and supported parameter behavior; check current account access |

Local inspection and construction tests confirmed the pinned adapter signatures accept
`anthropic/claude-sonnet-5`, `scribe_v2_realtime`, explicit ElevenLabs TTS models/voice IDs, and
the OpenRouter factory. This is construction evidence, not a successful provider request or an
account-access guarantee. Do not invent a replacement model or silently use LiveKit Inference.

Exact installed CLI syntax and the commands that worked are recorded in `docs/compatibility.md`.
The starter template was inspected but not copied because its cloud/provider defaults conflict
with this architecture. Do not run a console-only demo and claim the same-room requirement passed.

Architecture choices, dependency boundaries, queue contracts, rubrics and failure policies in this package are application design decisions. They are not assertions that LiveKit provides all of these behaviors automatically.
