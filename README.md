# LiveKit Interview Agent

A voice AI agent that interviews a participant over LiveKit through three topics — name & age,
role, and an adaptive deep-dive generated from the role — with a Next.js frontend to join the room
and watch progress live. See [docs/plans/2026-09-06-livekit-interview-agent-scaffold.md](docs/plans/2026-09-06-livekit-interview-agent-scaffold.md)
for the full design.

## Stack

- **Agent worker** (`packages/agent`) — [LiveKit Agents JS](https://docs.livekit.io/agents/), ElevenLabs (STT + TTS), OpenRouter (LLM)
- **Web app** (`apps/web`) — Next.js 16, [`@livekit/components-react`](https://github.com/livekit/components-js)
- **Database** (`packages/db`) — SQLite via drizzle-orm / better-sqlite3
- **Domain logic** (`packages/core`) — schemas, interview state machine, prompts (framework-free)

## Prerequisites

- Node.js ≥ 22, [pnpm](https://pnpm.io/) 11.x
- A LiveKit server — either **run one locally with Docker** (below) or a
  [LiveKit Cloud](https://cloud.livekit.io/) project
- An [ElevenLabs](https://elevenlabs.io/) API key and a voice ID
- An [OpenRouter](https://openrouter.ai/) API key and a chosen model (any model with solid
  function-calling support — nothing is hardcoded)

## 1. Install dependencies

```bash
pnpm install
```

## 2. Start a LiveKit server

### Option A — local, with Docker (no LiveKit account needed)

```bash
docker run -d --name livekit-dev \
  -p 7880:7880 -p 7881:7881 -p 7882:7882/udp \
  livekit/livekit-server --dev --bind 0.0.0.0
```

Dev mode uses fixed placeholder credentials — `devkey` / `secret` — and needs no config file.
Verify it's up:

```bash
curl http://localhost:7880/   # -> OK
```

Stop/restart later with `docker stop livekit-dev` / `docker start livekit-dev`. Remove it with
`docker rm -f livekit-dev`.

### Option B — LiveKit Cloud

Create a project at [cloud.livekit.io](https://cloud.livekit.io/) and grab its URL, API key, and
API secret from project settings.

## 3. Configure environment

Copy the template and fill it in:

```bash
cp .env.example .env
```

| Variable                  | Local Docker (Option A) | LiveKit Cloud (Option B)     |
| ------------------------- | ----------------------- | ---------------------------- |
| `LIVEKIT_URL`             | `ws://localhost:7880`   | your project's `wss://…` URL |
| `LIVEKIT_API_KEY`         | `devkey`                | your project's API key       |
| `LIVEKIT_API_SECRET`      | `secret`                | your project's API secret    |
| `NEXT_PUBLIC_LIVEKIT_URL` | `ws://localhost:7880`   | same as `LIVEKIT_URL`        |

Also required, either way:

- `ELEVENLABS_API_KEY`, `ELEVEN_VOICE_ID` — from your ElevenLabs account
- `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` — from your OpenRouter account (e.g.
  `openai/gpt-4o-mini`, or any other function-calling-capable model)

`LIVEKIT_AGENT_NAME` and `DATABASE_URL` already have working defaults in `.env.example` — leave
them as-is unless you have a reason to change them.

Everything under **Latency tuning** in `.env.example` is optional; the agent uses the documented
defaults when the keys are absent. See [Tuning responsiveness](#tuning-responsiveness) below.

`.env` is gitignored; never commit real keys.

## 4. Set up the database

```bash
pnpm db:migrate
```

Creates `data/interviews.db` and applies the schema. Safe to re-run.

## 5. Run it

```bash
pnpm dev
```

This builds `packages/core`/`packages/db`, then starts the agent worker and the Next.js app
together. Open **http://localhost:3000**, enter a name, and you'll be dropped into a room the
agent joins automatically (explicit dispatch — the token asks for the `interviewer` agent by
name).

To run them separately instead:

```bash
pnpm build:libs     # once, or after editing packages/core or packages/db
pnpm dev:agent      # terminal 1
pnpm dev:web        # terminal 2
```

## After an interview

Each interview gets a UUID; visit `http://localhost:3000/interviews/<id>` for the results page
(name, age, role, and the full deep-dive transcript), or hit `GET /api/interviews/<id>` for the
raw JSON. Every write happens as the interview progresses — killing the process mid-call leaves
whatever topics were already answered (`status: 'in_progress'`) rather than losing them.

## Tuning responsiveness

The agent is configured for a short turnaround out of the box: an in-process end-of-turn detector
(no network hop per pause), preemptive LLM _and_ TTS generation, a 300 ms endpointing floor,
ElevenLabs Flash with text normalisation off, a capped reply length, and a hard deadline on the
probe-plan call. The models and the SQLite handle are built once per worker process in `prewarm`
rather than per call, so a participant never waits on connection setup.

Every knob lives in `.env` (see `.env.example` for the full list with defaults):

| Variable                                               | Effect                                                                                                 |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| `TURN_DETECTOR`                                        | `v1-mini` (default, local) / `v1` (cloud, LiveKit Cloud only) / `vad` / `stt`                          |
| `ENDPOINTING_MIN_DELAY_MS`, `ENDPOINTING_MAX_DELAY_MS` | Silence before the agent takes the turn. Lower is snappier, and more likely to interrupt.              |
| `PREEMPTIVE_TTS`                                       | Synthesise before the turn is confirmed. Set `false` to trade latency for fewer wasted TTS characters. |
| `LLM_MAX_TOKENS`, `LLM_TEMPERATURE`                    | Reply length and variability. A long reply is experienced as slowness.                                 |
| `PROBE_PLANNER_MODEL`, `PROBE_PLANNER_TIMEOUT_MS`      | The call that builds topic 3 from topic 2 — the longest pause in the interview.                        |

**The biggest single win is `OPENROUTER_MODEL`.** Everything above shaves off round trips around
the model; the model's own time-to-first-token dominates them all. If the agent still feels slow,
try a smaller/faster model there first — and if you want topic 3's questions written by a large
model without paying for its latency mid-conversation, leave `OPENROUTER_MODEL` small and set
`PROBE_PLANNER_MODEL` to the larger one (or the reverse).

## Other commands

| Command                     | Does                                                                     |
| --------------------------- | ------------------------------------------------------------------------ |
| `pnpm build`                | Production build of every package                                        |
| `pnpm typecheck`            | `tsc --noEmit` across the workspace                                      |
| `pnpm test`                 | Runs every package's test suite (vitest)                                 |
| `pnpm lint` / `pnpm format` | ESLint / Prettier                                                        |
| `pnpm db:generate`          | Regenerate a drizzle migration after editing `packages/db/src/schema.ts` |

## Troubleshooting

- **"Invalid agent configuration" on `pnpm dev:agent`** — a required env var is missing; the error
  lists every one that's unset.
- **Agent never joins the room** — confirm the LiveKit server is reachable
  (`curl $LIVEKIT_URL` won't work directly since it's a `ws://`/`wss://` URL, but
  `curl http://localhost:7880/` should return `OK` for the local Docker setup), and that
  `LIVEKIT_AGENT_NAME` matches on both the worker and what the token route dispatches (`interviewer`
  by default on both sides).
- **`pnpm run build` fails after editing `packages/core` or `packages/db`** — run
  `pnpm build:libs` first; `apps/web` consumes their compiled `dist/` output, not their TypeScript
  source directly.
