# LiveKit Voice Interview Agent — Scaffold

**Status:** done
**Tier:** structural — greenfield repository; this plan establishes every module boundary, every
dependency, and the persistence layer from nothing. Under the skill's "when torn, take the higher
tier" rule there is no lower tier available.
**Scope:** Scaffold a pnpm-workspace TypeScript application in which a LiveKit voice agent
interviews a human through three sequential topics — identity, role, and a deep-dive adaptively
generated from the role answers — holding answers in an in-process session cache and persisting
them to SQLite, with a Next.js frontend to join the room and watch progress.
**Out of scope (explicit non-goals):**

- Authentication / user accounts. The web app asks for a display name and nothing more.
- Multi-language interviews. English only; the language code is config, not a feature.
- Deployment, Docker, CI, LiveKit Cloud provisioning. Local dev only.
- Resuming an interrupted interview into a new room. A dropped participant marks the interview
  `abandoned`; it is not rejoinable in this scaffold.
- Analytics, dashboards, or any read UI beyond a single JSON result view.
- Telephony / SIP inbound.

---

## Orientation <!-- Phase 1 -->

The repository is **empty**. `git status` reports branch `master` with **no commits**; the only
tracked-adjacent content is `.claude/skills/`. Everything below is therefore a decision this plan
makes rather than a convention it discovered — which is why Phase 4's conformance ledger is
inverted (see the note there).

**Local toolchain (verified by running the commands):**

| Thing                         | Value               | How it was checked                |
| ----------------------------- | ------------------- | --------------------------------- |
| Node                          | v24.20.0            | `node -v`                         |
| npm                           | 11.19.1             | `npm -v`                          |
| pnpm                          | 11.25.0             | `pnpm -v`                         |
| Package manager for this repo | **pnpm workspaces** | chosen; pnpm is already installed |

**Dependency versions — resolved from the npm registry on 2026-09-06, not from memory.** Every
version below was read with `npm view <pkg> version`; the LiveKit ones were additionally
downloaded with `npm pack` and their `.d.ts` files read (see Sources).

| Package                             | Version    | Where used                                                      |
| ----------------------------------- | ---------- | --------------------------------------------------------------- |
| `@livekit/agents`                   | `1.8.0`    | agent worker                                                    |
| `@livekit/agents-plugin-elevenlabs` | `1.8.0`    | STT (Scribe) + TTS                                              |
| `@livekit/agents-plugin-openai`     | `1.8.0`    | LLM, pointed at OpenRouter                                      |
| `@livekit/agents-plugin-silero`     | `1.8.0`    | VAD (see "VAD" decision below — may be dropped)                 |
| `@livekit/rtc-node`                 | `0.13.34`  | **peer dep of `@livekit/agents`**, must be installed explicitly |
| `livekit-server-sdk`                | `2.18.0`   | token minting in the Next.js route                              |
| `livekit-client`                    | `2.22.2`   | peer dep of components-react                                    |
| `@livekit/components-react`         | `2.9.24`   | room UI                                                         |
| `@livekit/components-styles`        | `1.2.0`    | room UI baseline CSS                                            |
| `next`                              | `16.3.4`   | web app                                                         |
| `react` / `react-dom`               | `19.2.8`   | web app                                                         |
| `drizzle-orm`                       | `0.45.2`   | SQLite access                                                   |
| `drizzle-kit`                       | `0.31.10`  | migration generation                                            |
| `better-sqlite3`                    | `13.0.3`   | SQLite driver                                                   |
| `zod`                               | `^3.25.76` | tool schemas + domain validation — **pinned to 3.x, see below** |
| `typescript`                        | `~5.9.3`   | **not 7.x, see below**                                          |
| `tsx`                               | `4.23.13`  | run the agent in dev without a build step                       |
| `vitest`                            | `5.0.0`    | tests                                                           |
| `dotenv`                            | `17.4.2`   | env loading in the agent/db packages                            |

Three version decisions that a cold reader would otherwise get wrong:

1. **`typescript` is pinned to `~5.9.3`, not the `latest` tag.** `npm view typescript dist-tags`
   returns `latest: 7.0.2` — TypeScript 7, the native port. `@livekit/agents@1.8.0` itself builds
   against `typescript: ^5.0.0` (its own devDependencies). Next 16, drizzle-kit and vitest are all
   released against 5.x. Using 5.9.3 keeps the whole toolchain on tested ground; TS 7 is a
   deliberate later upgrade, not a scaffold decision.
2. **`zod` is pinned to `^3.25.76`, not 4.x.** `@livekit/agents@1.8.0` declares
   `peerDependencies.zod: "^3.25.76 || ^4.1.8"` — both are _allowed_ — but its own devDependencies
   test against `^3.25.76`, and tool-parameter schemas are converted through
   `zod-to-json-schema@^3.24.6`, which is a zod-3 tool. 3.x is the path the framework actually
   exercises. Revisit only if a zod-4-only feature is needed.
3. **`better-sqlite3@13.0.3` installs as a prebuilt binary on Node 24 — verified, not assumed.**
   A throwaway install plus `new Database(':memory:')`, `create table`, `insert`, `select` round
   trip succeeded on v24.20.0 in 4 seconds with no compile step. This removes the usual
   "will the native module build?" risk from the plan.

**Build / run / test commands (established by this plan, root `package.json` scripts):**

```
pnpm dev            # concurrently: agent worker (dev mode) + next dev
pnpm dev:agent      # pnpm --filter @interview/agent dev   -> tsx src/main.ts dev
pnpm dev:web        # pnpm --filter @interview/web dev     -> next dev
pnpm build          # pnpm -r build
pnpm typecheck      # pnpm -r exec tsc --noEmit
pnpm test           # pnpm -r test  -> vitest run
pnpm db:generate    # pnpm --filter @interview/db generate -> drizzle-kit generate
pnpm db:migrate     # pnpm --filter @interview/db migrate  -> tsx src/migrate.ts
```

**Test setup:** none exists. This plan creates it: `vitest` per package, tests colocated as
`*.test.ts` beside the unit under test. The agent package additionally uses the framework's own
harness — `AgentSession.run({ userInput, outputType })`
(`node_modules/@livekit/agents/dist/voice/agent_session.d.ts:524`) drives an agent turn with **no
room, no audio, and no LiveKit server**, returning a `RunResult` for assertions. That is what makes
the interview logic testable without a live room, and every agent-side verification step in this
plan leans on it.

**Migration tooling and workflow:** drizzle-kit. `pnpm db:generate` writes SQL into
`packages/db/drizzle/`; `pnpm db:migrate` applies it. **SQL migration files are generated output —
never hand-edit them.** Change `packages/db/src/schema.ts` and regenerate.

**Generated / never-hand-edit paths:**

- `packages/db/drizzle/**` — drizzle-kit output
- `packages/db/drizzle/meta/**` — drizzle-kit snapshots
- `pnpm-lock.yaml`
- `apps/web/.next/**`
- any `dist/**`
- `data/*.db` — the SQLite file itself

**Lint/format:** none configured yet. This plan adds Prettier + ESLint flat config at the root but
treats them as scaffolding, not as a source of conventions to conform to.

---

## Hard constraints (this project) <!-- Phase 2 -->

There is no project documentation to lift constraints from — the repository is empty. The binding
constraints therefore come from the framework typings and source that were read directly, and they
are hard in the sense that violating them fails at runtime:

- **`AgentTask.run()` may only be awaited from inside a function tool or from an Agent's
  `onEnter` / `onExit`.** The implementation checks for an inline-task context and throws
  otherwise: `"should only be awaited inside function tools or the onEnter/onExit methods of an
Agent"` — source: `@livekit/agents@1.8.0` `dist/voice/agent.js:474`, guarded by the
  `Task.current()` check at `dist/voice/agent.js:469`. _This single constraint determines the
  orchestration design in Phase 5; a plan that awaited the three topic tasks from the job
  entrypoint would not run._
- **`@livekit/rtc-node` is a peer dependency of `@livekit/agents`, not a transitive one**
  (`peerDependencies: { "@livekit/rtc-node": "^0.13.34", "zod": "^3.25.76 || ^4.1.8" }`) — source:
  `@livekit/agents@1.8.0` `package.json`. Under pnpm's strict node_modules this **must** be an
  explicit dependency of `packages/agent` or imports fail.
- **The agent entry file must have a `defineAgent(...)` result as its default export**, because
  the worker dynamically imports it by path: `ServerOptions.agent` is documented as "Path to a file
  that has {@link Agent} as a default export, dynamically imported later for entrypoint and prewarm
  functions" — source: `dist/worker.d.ts:68-71`.
- **`@livekit/agents-plugin-openai` has no `withOpenRouter` helper.** A `grep -i openrouter` over
  the whole plugin `dist/` returns nothing; the statics are `withAzure`, `withCerebras`,
  `withFireworks`, `withXAI`, `withGroq`, `withDeepSeek` — source: `dist/llm.d.ts:48-125`.
  OpenRouter must be configured through the generic `baseURL` / `apiKey` / `client` options on
  `LLMOptions` — source: `dist/llm.d.ts:5-21`.
- **No credentials in this plan or in any committed file.** Keys are referenced by env var name
  only; `.env` is gitignored and `.env.example` carries empty placeholders.

---

## Sources read <!-- Phase 2 -->

No repository documentation exists (no README, no ADRs, no `CLAUDE.md`, no `CONTRIBUTING.md`, no
prior plans in `docs/plans/`) — the directory contained only `.claude/skills/`. The sources below
are the vendored package typings and compiled sources, downloaded with `npm pack` at the exact
versions this plan pins and read in full. **Paths are given as they will exist after `pnpm
install`; the line numbers are from the 1.8.0 / 2.18.0 / 0.13.34 tarballs.**

| Document                                                                 | What it settled                                                                                                                                                                                                      |
| ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `@livekit/agents/dist/voice/agent.d.ts:95-160`                           | `Agent` options shape: `instructions`, `tools`, per-agent `stt`/`llm`/`tts`/`vad` overrides, `onEnter`/`onExit` hooks (`:136`)                                                                                       |
| `@livekit/agents/dist/voice/agent.d.ts:161-171`                          | `AgentTask<ResultT, UserData>` exists, with `complete(result)` and `run(): Promise<ResultT>` — the typed sub-conversation primitive the three topics are built on                                                    |
| `@livekit/agents/dist/voice/agent.js:459-560`                            | `run()` swaps the session's active agent to the task, awaits `complete()`, then restores the previous agent; and enforces the inline-task constraint at `:469` / `:474`                                              |
| `@livekit/agents/dist/voice/agent_session.d.ts:139-231`                  | `AgentSessionOptions`: `stt`, `tts`, `llm`, `vad`, **`userData`** (`:150`), `turnHandling`, `userAwayTimeout`. VAD is **auto-provisioned** from bundled inference when omitted; pass `null` to opt out               |
| `@livekit/agents/dist/voice/agent_session.d.ts:422-543`                  | `session.userData` getter/setter, `start({agent, room})`, `say()`, `generateReply()`, `updateAgent()`, `currentAgent`, and `run<T>({userInput, outputType})` — the no-room test harness                              |
| `@livekit/agents/dist/voice/events.d.ts:41-100`                          | Session events available for the transcript/progress feed: `user_input_transcribed` (with `isFinal`), `agent_state_changed`, `user_state_changed`, `metrics_collected`                                               |
| `@livekit/agents/dist/llm/tool_context.d.ts:309-373`                     | `tool({ name, description, parameters, execute })` — `parameters` accepts **a Zod object schema** with inferred arg types; `execute(args, { ctx })` gets a `RunContext`                                              |
| `@livekit/agents/dist/voice/run_context.d.ts:100-115`                    | `RunContext.userData` — how a tool reads and mutates the shared session state                                                                                                                                        |
| `@livekit/agents/dist/llm/tool_context.d.ts:62-76`                       | `handoff({ agent, returns })` — the _alternative_ topic-sequencing mechanism, rejected in Phase 5                                                                                                                    |
| `@livekit/agents/dist/generator.d.ts`                                    | `defineAgent({ entry, prewarm, onSessionEnd })` — `onSessionEnd` runs after the session closes and before the report, bounded by `ServerOptions.sessionEndTimeout`                                                   |
| `@livekit/agents/dist/worker.d.ts:36-100`                                | `ServerOptions` fields: `agent` (path, default-export contract), `agentName` (enables **explicit dispatch**, defaults from `LIVEKIT_AGENT_NAME`), `wsURL`, `apiKey`, `apiSecret`, `numIdleProcesses`                 |
| `@livekit/agents/dist/cli.d.ts`                                          | `cli.runApp(new ServerOptions({ agent: import.meta.filename }))` is the worker entrypoint idiom; gives `dev` / `start` subcommands                                                                                   |
| `@livekit/agents/dist/job.d.ts:60-129`                                   | `JobContext`: `room`, `connect()`, `waitForParticipant()`, `addShutdownCallback()`                                                                                                                                   |
| `@livekit/agents-plugin-elevenlabs/dist/stt.d.ts`                        | `STT` supports `model: 'scribe_v2_realtime'`, `useRealtime`, `sampleRate`, `serverVad`, `languageCode`, `keyterms`. Confirms **Scribe realtime streaming STT is supported**, which the user's choice depends on      |
| `@livekit/agents-plugin-elevenlabs/dist/tts.d.ts` + `models.d.ts`        | `TTS` options `voiceId`, `model`, `voiceSettings`, `streamingLatency`; valid models include `eleven_flash_v2_5`                                                                                                      |
| `@livekit/agents-plugin-openai/dist/llm.d.ts:5-21`                       | `LLMOptions` — `baseURL`, `apiKey`, `client`, `model`, `temperature`, `strictToolSchema`                                                                                                                             |
| `@livekit/agents-plugin-openai/dist/llm.js:8`                            | `strictToolSchema` defaults to **`false`** — so no extra work is needed for OpenRouter models that reject OpenAI strict schemas                                                                                      |
| `livekit-server-sdk/dist/AccessToken.d.ts:74-82` + `dist/grants.d.ts:82` | `AccessToken.roomConfig` accepts a `RoomConfiguration`; `RoomConfiguration` and `RoomAgentDispatch` are re-exported from `livekit-server-sdk/dist/index.d.ts` — this is how the browser token requests a named agent |
| `@livekit/rtc-node/dist/participant.d.ts:51-161`                         | Agent→browser channels: `sendText(text, {topic})` (`:66`), `publishData`, `setAttributes` (`:117`), `registerRpcMethod` (`:155`)                                                                                     |
| `@livekit/rtc-node/dist/room.d.ts:124`                                   | `registerTextStreamHandler(topic, cb)` — the browser side of the progress channel                                                                                                                                    |
| `@livekit/components-react` npm metadata                                 | `peerDependencies: { react: ">=18", "react-dom": ">=18", "livekit-client": "^2.20.1" }` — React 19 / Next 16 are compatible                                                                                          |

---

## Context <!-- Phase 3 -->

The five Phase 3 questions are answered against the **framework**, since the repository has no code
of its own. Every answer carries a `path:line` anchor into the pinned package sources listed above.

**1. Which module and layer does the change belong to, and what are the boundaries?**
All four modules are created here. The dependency direction is strictly one-way:

```
      apps/web ──────────────┐
                             ├──> packages/core   (pure: types, zod schemas, prompts, state machine)
      packages/agent ────────┤
                             └──> packages/db     (drizzle schema + repositories)
      packages/db ──────────────> packages/core
```

`packages/core` imports nothing from the workspace and nothing from LiveKit, ElevenLabs, OpenRouter,
or the database. That is the boundary that makes the interview logic unit-testable with plain
`vitest` and no network.

**2. Closest structurally similar existing feature — the reference implementation.**
There is no in-repo prior art, so the reference implementation is the framework's own documented
idiom, which this scaffold deliberately reads as a sibling of:

> **Reference implementation:** the `defineAgent` + `cli.runApp(new ServerOptions({ agent:
import.meta.filename }))` worker idiom documented at
> `node_modules/@livekit/agents/dist/cli.d.ts:6-14`, combined with the
> `AgentTask` sub-conversation pattern at `node_modules/@livekit/agents/dist/voice/agent.js:459`.

Concretely, `packages/agent/src/main.ts` will read like the `cli.d.ts` example verbatim, and each
topic module will read like a `AgentTask` subclass whose single tool calls `this.complete(...)`.

**3. Naming, file-layout and export conventions in that area.**
Read off the framework packages themselves: ESM-only (`"type": "module"`), `exports` map with
`import`/`require` conditions, `.js` extensions on relative imports inside TypeScript source
(the framework's own `dist/index.d.ts` does `export * from './job.js'`), named exports rather than
default exports everywhere **except** the agent entry file, where the worker contract requires a
default export (`dist/worker.d.ts:68`). Files are `snake_case` in the framework
(`agent_session.ts`, `tool_context.ts`); this scaffold follows `kebab-case` for its own files
instead — see Deviations.

**4. How that area handles errors, validation, logging, config, transactions.**

- **Validation:** Zod, at the tool boundary. `tool({ parameters: <zod schema> })` parses model
  arguments before `execute` is called — `dist/llm/tool_context.d.ts:315-326`.
- **Errors:** `ToolError` for tool failures the model should see; `StopResponse`
  (`dist/voice/agent.d.ts:41`) to suppress a reply. `AgentTask.complete(new Error(...))` rejects
  the awaiting orchestrator — `dist/voice/agent.js:449`.
- **Logging:** the framework uses `pino` (`dependencies.pino: ^8.19.0`) and exports `log()` from
  `dist/log.js`. This scaffold uses the framework's `log()` in the agent package rather than adding
  a second logger.
- **Config:** environment variables read at process start; the worker itself reads
  `LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` / `LIVEKIT_AGENT_NAME`
  (`dist/worker.d.ts:54-57, 92`).
- **Transactions:** not applicable to the framework; on the DB side, drizzle's `db.transaction()`.

**5. End-to-end flow of the reference implementation.**

```
livekit server dispatches job
  -> worker (ServerOptions.agent path) dynamically imports the default export
  -> prewarm(proc)                       [load VAD once per process]
  -> entry(ctx: JobContext)
       -> ctx.connect()
       -> new AgentSession({ stt, llm, tts, vad, userData })
       -> session.start({ agent, room: ctx.room })
            -> agent.onEnter()           [inline-task context]
                 -> await task.run()     [swaps active agent, awaits complete()]
       -> ctx.addShutdownCallback(...)  /  defineAgent.onSessionEnd(ctx)
```

---

## Architecture conformance <!-- Phase 4 -->

**Note on an inverted ledger.** Phase 4 normally records conventions observed _in the repository_.
This repository is empty, so there are none. The ledger below records the conventions this scaffold
adopts **from the framework it embeds**, with the same evidence discipline — because for a
greenfield project embedding a framework, "conform before you improve" means conforming to the
framework's idiom rather than inventing a house style on day one.

| Convention observed                                      | Evidence                                                                                       | How this change follows it                                                                          |
| -------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| ESM-only packages, `"type": "module"`                    | `@livekit/agents/package.json` `exports` map with `import`/`require` conditions                | Every workspace package is `"type": "module"`; `tsconfig` uses `module: "NodeNext"`                 |
| Relative imports carry a `.js` extension                 | `@livekit/agents/dist/index.d.ts` — `export * from './job.js'`                                 | All intra-package relative imports written as `./foo.js`                                            |
| Agent entry file default-exports `defineAgent(...)`      | `dist/worker.d.ts:68-71`                                                                       | `packages/agent/src/interviewer.ts` default-exports `defineAgent({...})`; `main.ts` passes its path |
| Worker started via `cli.runApp(new ServerOptions(...))`  | `dist/cli.d.ts:6-14`                                                                           | `packages/agent/src/main.ts` is a near-verbatim copy of that example                                |
| Tool arguments validated by a Zod schema at the boundary | `dist/llm/tool_context.d.ts:315-326`                                                           | Every `record_*` tool declares `parameters` as a zod object exported from `packages/core`           |
| Per-agent model overrides layer over session defaults    | `AgentOptions.stt/llm/tts` at `dist/voice/agent.d.ts:80-90` vs `AgentSessionOptions` at `:139` | Models configured **once** on the session; topic tasks override nothing                             |
| Sub-conversations return typed results via `AgentTask`   | `dist/voice/agent.d.ts:161-171`                                                                | Each topic is an `AgentTask<TopicResult>`                                                           |
| Shared mutable state travels in `session.userData`       | `dist/voice/agent_session.d.ts:150`, `dist/voice/run_context.d.ts:100`                         | The in-memory interview cache **is** `userData`; tools reach it via `opts.ctx.userData`             |
| Framework logging via `log()` (pino)                     | `@livekit/agents` `dependencies.pino`, `dist/log.js`                                           | Agent package uses `log()`; no second logger added                                                  |
| Migrations are generated, never hand-written             | drizzle-kit's documented `generate` workflow                                                   | `packages/db/drizzle/**` marked generated; schema is the only edited artifact                       |

**Deviations:**

1. **File naming — `kebab-case` instead of the framework's `snake_case`.**
   _Why unavoidable:_ the workspace also contains a Next.js app, where `kebab-case` (and
   `PascalCase` for components) is the overwhelming ecosystem norm; `snake_case` route and component
   files would look wrong in `apps/web` and split the repo into two naming styles anyway.
   _Cost:_ file names in `packages/agent` do not visually match the framework source a developer
   may be reading alongside them. Import paths and symbol names are unaffected.
   _Reconciliation:_ none needed — it is a leaf-level cosmetic choice; if it ever matters, a rename
   is mechanical and touches only relative import specifiers.

2. **`vitest` rather than the framework's own test runner.**
   _Why unavoidable:_ `@livekit/agents` ships tests compiled into `dist` (`stt.test.js`) but exposes
   no runner for consumers; the assertion helpers it _does_ expose (`voice.testing`, `RunResult`)
   are runner-agnostic.
   _Cost:_ none material — `AgentSession.run()` returns a `RunResult` whose `.expect` chain works
   under any runner.
   _Reconciliation:_ n/a.

---

## Design <!-- Phase 5 -->

### Forces

Each force is drawn from the stated requirements, and every abstraction below traces back to one.

- **F1 — Three topics must run in a fixed order, and topic 3 cannot begin until topic 2's answers
  exist.** From the request ("first his name and age", "second ask across his title and job
  description", "topic three from information from topic two"). This is a _sequencing_ requirement,
  and it is the dominant force: it rules out designs where the LLM decides what to ask next.
- **F2 — Each topic yields structured data, not prose.** "his name and age", "his title and job
  description" are fields. The system must end with typed values, not a transcript to be mined
  later.
- **F3 — Topic 3's content is unknown until runtime.** "if he say he is software engineer and using
  c# must ask him everything across his work and so on" — the question set is a function of topic
  2's output, and "and so on" means the design must not hardcode a list of professions.
- **F4 — Answers must survive the room.** The user asked for an in-memory cache _while in the room_
  **and** SQLite persistence. A crash or a hangup mid-interview must not lose completed topics.
- **F5 — A human is on the other end of a voice call.** People give partial answers, ramble,
  mis-hear, and interrupt. A topic is not complete because a question was asked; it is complete
  when a valid answer has been captured.
- **F6 — The interview logic must be verifiable without a LiveKit server, microphone, or paid API
  calls.** Nothing in the request says this, but without it no step in Phase 6 can be verified
  cheaply, and the first regression will be found in production.
- **F7 — Three external services can each fail independently** (ElevenLabs STT, ElevenLabs TTS,
  OpenRouter). They are separate vendors on separate credentials.
- **F8 — The browser must show the participant where they are in the interview.** Implied by
  "make room with agent" plus a full Next.js frontend: a voice-only black box with no visible state
  is not a usable demo.

### Approach

A single **orchestrator agent** owns the interview and runs three **typed sub-conversations** in
sequence from its `onEnter` hook. Each sub-conversation is an `AgentTask<T>` — the framework
primitive that swaps itself in as the active agent, converses until a tool calls `complete(value)`,
then restores the previous agent and returns `value` to the awaiting caller
(`dist/voice/agent.js:459-560`).

```ts
// packages/agent/src/interview/orchestrator.ts  — shape, not final code
class InterviewOrchestrator extends Agent<InterviewUserData> {
  async onEnter() {
    const s = this.session;
    await s.say(GREETING);

    const identity = await new IdentityTask().run(); // F1, F2
    s.userData.record('identity', identity); // F4 (cache + write-through)

    const role = await new RoleTask().run();
    s.userData.record('role', role);

    const plan = await buildProbePlan(role, s.userData); // F3
    const deepDive = await new DeepDiveTask(plan).run();
    s.userData.record('deepDive', deepDive);

    await s.say(CLOSING);
    s.userData.markComplete();
  }
}
```

Sequencing therefore lives in **ordinary awaited TypeScript**, not in a prompt and not in the
model's discretion. The model's only jobs are conducting each conversation and filling in one
structured tool call per topic.

Topic 3's adaptivity (F3) is a two-stage move: a **probe planner** makes one non-voice LLM call
that turns `RoleAnswer` into an ordered list of probe questions tailored to the stated domain and
technologies, and `DeepDiveTask` then walks that list conversationally, recording one
question/answer pair at a time. Planning is separated from asking so the plan is inspectable,
testable against a fake LLM (F6), loggable, and shippable to the browser as progress (F8) — none of
which is true if topic 3 is "a clever prompt".

### Patterns

| Concern                                        | Pattern                                                                                                                                              | Force  | Prior art                                                                                                     | Rejected alternative — reason                                                                                                                                                                                                                                                                                       |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Running three topics in a fixed order          | Sequential `await` of `AgentTask<T>` from `onEnter`                                                                                                  | F1, F2 | `AgentTask` at `dist/voice/agent.d.ts:161`; run semantics at `dist/voice/agent.js:459`                        | **`handoff({agent})` from a tool** (`dist/llm/tool_context.d.ts:73`) — handoff hands control _to_ the next agent and returns nothing to a caller, so ordering would live in prompts and topic results would have to be scraped from `userData` by convention. Sequencing is a program concern, not a model concern. |
| Capturing each topic's answer as typed data    | One `tool()` per topic whose Zod `parameters` **are** the result type, calling `complete(args)`                                                      | F2, F5 | `tool({parameters: <zod>})` at `dist/llm/tool_context.d.ts:315-326`                                           | **Post-hoc extraction from the transcript** — a second LLM pass, a second failure mode, and no natural point at which the topic is "done".                                                                                                                                                                          |
| Deciding a topic is finished                   | The task completes only when its tool fires; the tool's Zod schema is the completeness check                                                         | F5     | `AgentTask.complete` at `dist/voice/agent.js:445`                                                             | **Turn counting / "ask 3 questions then move on"** — moves on with missing answers when the human rambles.                                                                                                                                                                                                          |
| Making topic 3 depend on topic 2               | Probe-planner function: `(RoleAnswer) => ProbePlan`, one structured LLM call, zod-validated, with a static per-domain fallback                       | F3, F7 | The plugin's plain `OpenAI` client (`LLMOptions.client`, `dist/llm.d.ts:12`)                                  | **Hardcoded question banks per profession** — cannot satisfy "and so on". **Pure prompt injection with no plan object** — nothing to test, log, or display.                                                                                                                                                         |
| Sharing interview state across tasks and tools | `AgentSession.userData` holding one `InterviewSessionState` object                                                                                   | F4     | `userData` at `dist/voice/agent_session.d.ts:150`; `RunContext.userData` at `dist/voice/run_context.d.ts:100` | **A module-level singleton keyed by room name** — breaks the moment one worker process handles two jobs, which is the default (`numIdleProcesses`).                                                                                                                                                                 |
| Persisting without blocking the conversation   | Write-through repository: cache is authoritative in-room, each topic completion fires a fire-and-forget upsert; a final flush runs in `onSessionEnd` | F4     | `defineAgent.onSessionEnd` (`dist/generator.d.ts`), `ctx.addShutdownCallback` (`dist/job.d.ts:107`)           | **Persist only at the end** — a dropped call loses everything. **Await every write inline** — puts SQLite latency inside the speech loop.                                                                                                                                                                           |
| Keeping interview logic testable               | `packages/core` is pure — types, schemas, prompts, plan-building, and the state machine, with zero I/O imports                                       | F6     | Framework's own separation of `llm/` from provider plugins                                                    | **Logic inside the `Agent` subclasses** — then nothing can be tested without constructing a session.                                                                                                                                                                                                                |
| Provider failure handling                      | One `createModels()` factory per provider with explicit config validation at startup; missing/invalid keys fail the worker at boot, not mid-call     | F7     | `ServerOptions` reads its own env at construction (`dist/worker.d.ts:54-57`)                                  | **Lazy per-request construction** — surfaces a missing key as a silent dead room.                                                                                                                                                                                                                                   |
| Showing progress in the browser                | Agent pushes a JSON snapshot on `sendText(..., {topic:'interview.progress'})`; web registers `registerTextStreamHandler`                             | F8     | `dist/participant.d.ts:66`, `dist/room.d.ts:124`                                                              | **Polling a REST endpoint** — adds an API surface and lags the conversation. **Participant attributes** — capped and awkward for a growing Q&A list.                                                                                                                                                                |
| Persistence access                             | Repository module (`packages/db/src/repositories/interviews.ts`) exposing intent-named functions                                                     | F4     | drizzle's own query builder                                                                                   | **Calling drizzle directly from the agent** — puts SQL in the conversation layer and gives the web app a second, divergent query path.                                                                                                                                                                              |

### SOLID review

- **S — Single responsibility.** `IdentityTask` conducts one conversation; `interviewStateSchema`
  defines shape; `buildProbePlan` turns a role into questions; `InterviewRepository` writes rows.
  The concrete test: changing the _wording_ of the age question touches only
  `packages/core/src/prompts/identity.ts`, and changing _where answers are stored_ touches only
  `packages/db` — neither touches the other.
- **O — Open/closed.** Adding a fourth topic means writing one `AgentTask` + one zod schema and
  adding one line to `onEnter`'s sequence. No existing topic, tool, or table column is modified;
  `deep_dive_turns` and the progress payload are already keyed by topic id.
- **L — Liskov.** `IdentityTask`, `RoleTask` and `DeepDiveTask` all extend `AgentTask<T>` and are
  used **only** through `run(): Promise<T>`. None of them strengthens a precondition or relies on
  the orchestrator knowing which subclass it holds — the orchestrator awaits three different `T`s
  through one identical contract.
- **I — Interface segregation.** The web app imports `InterviewResult` types from
  `packages/core` and read-only query functions from `packages/db`; it never sees `ProbePlan`,
  tool definitions, or any LiveKit agent type. The agent never imports a React component or a
  drizzle table object — only repository functions.
- **D — Dependency inversion.** `buildProbePlan` takes a `ProbePlanner` interface
  (`{ plan(role: RoleAnswer): Promise<ProbePlan> }`), and the OpenRouter-backed implementation is
  injected in `packages/agent`. That is what lets the topic-3 logic be tested against a stub
  planner with no network (F6), and it is the one place this design pays for an interface — see the
  extension table for why the second implementation already exists.

### Extension points

| Extension point                                | Mechanism                                                                   | Variation anticipated                                         | Why plausible now                                                                                                                                                                                                |
| ---------------------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ProbePlanner` interface                       | Constructor injection into `DeepDiveTask`                                   | A deterministic stub planner alongside the OpenRouter planner | **Both implementations are written in this plan** — the stub is what Step 6's test runs against. It is not anticipated, it is required.                                                                          |
| `InterviewRepository` as a module of functions | Direct import; the agent depends on the function signatures, not on drizzle | Swapping SQLite for Postgres                                  | The user chose SQLite explicitly _after_ being offered Postgres; the boundary costs one file and is the difference between a driver swap and a rewrite of the agent.                                             |
| `createModels()` provider factory              | One function returning `{stt, tts, llm}`                                    | Switching STT vendor                                          | The user was asked STT-provider directly this session and chose ElevenLabs Scribe over Deepgram — a decision reversible in one function, and `@livekit/agents-plugin-deepgram@1.8.0` exists at the same version. |

Deliberately **not** extension points, because nothing today forces them: no plugin registry for
topics, no strategy interface for prompts, no abstraction over `AgentSession`, no repository
_interface_ with a single implementation, no event bus.

### Maintainability

- **Placement:** four packages along the dependency arrow in Context; nothing imports upward.
- **Reuse:** the zod schemas in `packages/core` are used three ways — as `tool()` parameters, as
  drizzle-write validation, and as the web app's response types. One definition, three consumers.
- **New dependencies:** every one is justified in Orientation; none duplicates another's job. The
  one judgement call is `@livekit/agents-plugin-silero` — the session **auto-provisions a bundled
  Silero VAD** when `vad` is omitted (`dist/voice/agent_session.d.ts:141-147`), so **start without
  the plugin** and add it only if the bundled path proves unsatisfactory. Step 3 verifies which.
- **Code this makes dead:** none — greenfield.
- **Naming:** topic modules are `identity-task.ts`, `role-task.ts`, `deep-dive-task.ts`; their
  result types `IdentityAnswer`, `RoleAnswer`, `DeepDiveAnswer`; their tools `record_identity`,
  `record_role`, `record_probe_answer`. The noun is the same in the file name, the type, the tool,
  and the DB column group.

---

## Steps <!-- Phase 6 -->

Each step leaves the repo in a working state. Steps 1-4 build a talking agent; 5-7 add the
interview; 8-10 add persistence and the browser.

1. **Workspace skeleton** — files: `package.json`, `pnpm-workspace.yaml`, `tsconfig.base.json`,
   `.gitignore`, `.env.example`, `.prettierrc`, `eslint.config.js`.
   Change: root workspace with `packages/*` and `apps/*`; the scripts listed in Orientation;
   `.gitignore` covering `node_modules`, `.next`, `dist`, `.env`, `data/*.db`; `.env.example` with
   empty `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `LIVEKIT_AGENT_NAME=interviewer`,
   `ELEVENLABS_API_KEY`, `ELEVEN_VOICE_ID`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`,
   `DATABASE_URL=./data/interviews.db`.
   Verify: `pnpm install` completes and `pnpm -r exec node -e "console.log(1)"` runs in every
   package.

2. **`packages/core` — domain types and schemas** — files: `src/types.ts`, `src/schemas.ts`,
   `src/state.ts`, `src/prompts/*.ts`, `src/index.ts`, `src/state.test.ts`.
   Change: zod schemas `identityAnswerSchema` (`fullName: string.min(1)`, `age: number.int().min(13).max(120)`),
   `roleAnswerSchema` (`jobTitle`, `jobDescription`, `domain`, `technologies: string[]`,
   `seniority: enum.optional()`), `probePlanSchema` (`{ topic: string, questions: string[] }`),
   `deepDiveAnswerSchema` (`{ turns: {question, answer}[], summary: string }`); the
   `InterviewSessionState` class (in-memory cache) with `record(topic, value)`, `snapshot()`,
   `markComplete()`, `status`, and an `onChange` callback hook; prompt builders as pure functions.
   No imports outside `zod`.
   Verify: `pnpm --filter @interview/core test` — `state.test.ts` asserts that recording topics out
   of order throws, that `snapshot()` is a deep copy, and that `onChange` fires once per record.

3. **`packages/agent` — a worker that connects and speaks** — files: `src/main.ts`,
   `src/interviewer.ts`, `src/config.ts`, `src/models.ts`.
   Change: `config.ts` validates env with zod at import time and throws a named error listing every
   missing key; `models.ts` exports `createModels()` returning
   `{ stt: new elevenlabs.STT({ model: 'scribe_v2_realtime', useRealtime: true, languageCode: 'en' }),
tts: new elevenlabs.TTS({ model: 'eleven_flash_v2_5', voiceId: env.ELEVEN_VOICE_ID }),
llm: new openai.LLM({ baseURL: 'https://openrouter.ai/api/v1', apiKey: env.OPENROUTER_API_KEY,
model: env.OPENROUTER_MODEL }) }` — **VAD omitted** so the bundled inference VAD is used;
   `interviewer.ts` default-exports `defineAgent({ entry })` where `entry` connects, starts an
   `AgentSession` with a placeholder `Agent` that says one sentence; `main.ts` is
   `cli.runApp(new ServerOptions({ agent: fileURLToPath(import.meta.url).replace('main','interviewer') }))`
   — resolve the entry path explicitly rather than relying on `import.meta.filename`.
   Verify: `pnpm dev:agent` prints `registered worker` and stays connected; then, in the LiveKit
   Agents Playground or via `lk room join`, the agent joins and is audible. **If the bundled VAD
   fails to load, add `@livekit/agents-plugin-silero` and pass `vad: await silero.VAD.load()` from
   `prewarm` — record which path was taken in the Outcome section.**

4. **Explicit dispatch wiring** — files: `packages/agent/src/main.ts`.
   Change: set `agentName: 'interviewer'` on `ServerOptions` so the worker only takes jobs that ask
   for it by name (`dist/worker.d.ts:87-94`).
   Verify: `pnpm dev:agent` logs the agent name; a room created **without** an agent dispatch gets
   no agent, and one created with `RoomAgentDispatch({ agentName: 'interviewer' })` does.

5. **Topics 1 and 2 as `AgentTask`s** — files: `src/interview/identity-task.ts`,
   `src/interview/role-task.ts`, `src/interview/orchestrator.ts`, `src/interview/tools.ts`.
   Change: each task extends `AgentTask<T>` with instructions from `packages/core/prompts` and one
   `tool()` whose `parameters` is the corresponding zod schema and whose `execute` calls
   `this.complete(args)`; `InterviewOrchestrator.onEnter` greets, then awaits the two tasks in
   order and records each into `session.userData`.
   Verify: `pnpm --filter @interview/agent test` — a vitest case builds an `AgentSession` with a
   **stub LLM** and drives `session.run({ userInput: "I'm Sam, twenty nine" })`, asserting the
   `record_identity` tool fires with `{fullName:'Sam', age:29}`. No room, no network
   (`agent_session.d.ts:524`).

6. **Topic 3 — probe planner and deep-dive task** — files: `packages/core/src/probe-plan.ts`
   (types + `ProbePlanner` interface + `StaticProbePlanner` fallback),
   `packages/agent/src/interview/probe-planner.ts` (OpenRouter implementation),
   `packages/agent/src/interview/deep-dive-task.ts`.
   Change: `OpenRouterProbePlanner.plan(role)` makes one `chat.completions.create` call on the same
   `OpenAI` client as the session LLM, requesting `response_format: {type:'json_object'}`, parses
   with `probePlanSchema`, retries once on a validation failure, and falls back to
   `StaticProbePlanner` (generic questions derived from `role.domain` and `role.technologies`) on a
   second failure. `DeepDiveTask` receives the plan, walks it question by question, and records each
   answer through a `record_probe_answer` tool, completing when the list is exhausted.
   Verify: `pnpm --filter @interview/core test` asserts `StaticProbePlanner` given
   `{jobTitle:'Software Engineer', technologies:['C#','.NET']}` produces questions naming C# and
   .NET; `pnpm --filter @interview/agent test` drives `DeepDiveTask` with a stub planner returning
   two fixed questions and asserts both are asked and both answers land in `userData`.

7. **`packages/db` — schema, migrations, repository** — files: `src/schema.ts`, `src/client.ts`,
   `src/repositories/interviews.ts`, `src/migrate.ts`, `drizzle.config.ts`.
   Change: the tables in Data/migrations below; `client.ts` opens `better-sqlite3` at
   `DATABASE_URL` with `PRAGMA journal_mode = WAL` and `PRAGMA foreign_keys = ON`;
   the repository exposes `createInterview`, `saveIdentity`, `saveRole`, `appendProbeTurn`,
   `appendTranscriptTurn`, `completeInterview`, `abandonInterview`, `getInterview`.
   Verify: `pnpm db:generate` emits SQL under `packages/db/drizzle/`; `pnpm db:migrate` applies it
   against a temp file; `pnpm --filter @interview/db test` round-trips a full interview through the
   repository against an in-memory database and asserts `getInterview` returns every field
   including ordered `deep_dive_turns`.

8. **Wire persistence into the agent** — files: `packages/agent/src/interview/persistence.ts`,
   `src/interviewer.ts`.
   Change: on `entry`, `createInterview({roomName, participantIdentity})` and put the id in
   `userData`; subscribe to `InterviewSessionState.onChange` to write through per topic; subscribe
   to the session's `user_input_transcribed` (final only) and agent speech events to append
   transcript turns; add `onSessionEnd` to `defineAgent` that calls `completeInterview` or
   `abandonInterview` depending on `userData.status`.
   Verify: run a full interview locally, then
   `sqlite3 data/interviews.db "select status, full_name, age, job_title from interviews;"` shows
   the completed row, and `select seq, question from deep_dive_turns order by seq;` shows the probe
   turns. Kill the worker mid-topic-2 and confirm the identity row persisted and status is
   `in_progress`.

9. **`apps/web` — token route and room** — files: `app/layout.tsx`, `app/page.tsx`,
   `app/api/token/route.ts`, `app/room/[roomName]/page.tsx`,
   `components/interview-room.tsx`, `components/mic-control.tsx`.
   Change: `/api/token` builds an `AccessToken` with a `roomJoin` grant and
   `token.roomConfig = new RoomConfiguration({ agents: [new RoomAgentDispatch({ agentName: 'interviewer' })] })`
   (`AccessToken.d.ts:76`, both classes re-exported from `livekit-server-sdk`); the room page
   renders `LiveKitRoom` + `RoomAudioRenderer` + `useVoiceAssistant`/`BarVisualizer` + a mic toggle.
   Verify: `pnpm dev` → open `http://localhost:3000`, enter a name, join; the agent joins the room
   and the greeting is audible in the browser; `useVoiceAssistant().state` visibly changes between
   `listening` and `speaking`.

10. **Progress + transcript UI, and the results view** — files:
    `packages/agent/src/interview/progress-publisher.ts`,
    `apps/web/components/progress-panel.tsx`, `apps/web/components/transcript-panel.tsx`,
    `apps/web/app/api/interviews/[id]/route.ts`, `apps/web/app/interviews/[id]/page.tsx`.
    Change: the agent serializes `state.snapshot()` and pushes it on every change via
    `ctx.room.localParticipant.sendText(json, { topic: 'interview.progress' })`
    (`participant.d.ts:66`); the browser reads it with
    `room.registerTextStreamHandler('interview.progress', …)` (`room.d.ts:124`) and renders the
    three topics with per-topic status and captured values; the transcript panel renders
    `user_input_transcribed` / agent transcriptions; the results page server-renders
    `getInterview(id)`.
    Verify: during a live interview the progress panel advances topic-by-topic as answers are
    given, and after hangup `/interviews/<id>` shows the same data read back from SQLite.

---

## Data / migrations <!-- Phase 6 -->

**Migration name:** `0000_init_interviews` (drizzle-kit generated from `packages/db/src/schema.ts`).

**Forward summary** — three tables, SQLite:

- `interviews` — `id TEXT PRIMARY KEY` (uuid), `room_name TEXT NOT NULL`,
  `participant_identity TEXT`, `status TEXT NOT NULL` (`in_progress` | `completed` | `abandoned`),
  `current_topic INTEGER NOT NULL DEFAULT 1`, `full_name TEXT`, `age INTEGER`, `job_title TEXT`,
  `job_description TEXT`, `domain TEXT`, `seniority TEXT`, `technologies TEXT` (JSON array),
  `probe_plan TEXT` (JSON), `deep_dive_summary TEXT`, `started_at INTEGER NOT NULL`,
  `updated_at INTEGER NOT NULL`, `completed_at INTEGER`. Index on `room_name`.
- `deep_dive_turns` — `id INTEGER PRIMARY KEY AUTOINCREMENT`,
  `interview_id TEXT NOT NULL REFERENCES interviews(id) ON DELETE CASCADE`, `seq INTEGER NOT NULL`,
  `question TEXT NOT NULL`, `answer TEXT NOT NULL`, `created_at INTEGER NOT NULL`.
  Unique index on `(interview_id, seq)`.
- `transcript_turns` — same key shape, plus `role TEXT NOT NULL` (`user` | `agent`),
  `text TEXT NOT NULL`.

Topic answers are stored as **columns on `interviews`** rather than as generic key/value rows
because the three topics are fixed and typed (F2); only the deep dive, whose length is unknown
(F3), gets its own table.

**Rollback plan:** the scaffold's only migration is the initial one and no production data exists,
so rollback is `rm data/interviews.db && pnpm db:migrate`. Once real interviews exist, generate a
new migration rather than editing `0000_init_interviews` — drizzle SQL files are generated output.

**Regeneration / reseed:** no seed data. `pnpm db:migrate` on a fresh checkout creates the file.

**Ordering constraints:** Step 7 (schema + migration) must land before Step 8 (agent writes).
`foreign_keys = ON` means an interview row must exist before any `deep_dive_turns` insert — hence
`createInterview` runs in `entry` before the session starts, not after the first answer.

---

## Risks & open questions

- **`AgentTask.run()` only works from a tool or `onEnter`/`onExit` (`agent.js:474`).** → The
  orchestrator drives everything from `onEnter`; Step 5's test exercises this path first, so a
  wrong assumption surfaces at the earliest possible step rather than at Step 10.
- **OpenRouter model quality for tool calling varies sharply by model, and a model that will not
  emit tool calls breaks every topic.** → `OPENROUTER_MODEL` is env-config, `strictToolSchema`
  already defaults to `false` (`plugin-openai/dist/llm.js:8`), and Step 5's stub-LLM test isolates
  our logic from model behaviour. Pick a model with first-class function-calling support.
- **Scribe v2 realtime turn-taking is less proven in JS than Deepgram** — the user chose it
  knowingly. → `createModels()` isolates the swap to one function; `@livekit/agents-plugin-deepgram@1.8.0`
  is available at the same version if latency or endpointing disappoints. Judge this at Step 3, not
  at Step 10.
- **Structured JSON from a non-OpenAI model may not honour `response_format`.** → The probe planner
  validates with zod, retries once, then falls back to `StaticProbePlanner`; topic 3 degrades in
  quality rather than failing.
- **`better-sqlite3` is synchronous, and the agent process is single-threaded.** → Writes are small,
  write-through and off the speech path; WAL mode is enabled. If write latency ever shows in
  metrics, batch through a queue — do not make the repository async-in-name-only.
- **Two processes (agent worker, Next.js) both open the same SQLite file.** → WAL mode supports one
  writer plus concurrent readers; the web app is **read-only** by design. Do not add writes to
  `apps/web`.
- **`age` collected by voice is error-prone** ("twenty nine", "I'm 29", "late twenties"). → The zod
  schema constrains `13..120`; on a parse failure the tool call is rejected and the model re-asks
  naturally, which is exactly the F5 behaviour wanted.
- [ ] _(non-blocking)_ Which OpenRouter model should be the default in `.env.example`? Any
      function-calling-capable model works; pick one at Step 3 and record it. Not blocking — the plan
      never hardcodes it.
- [ ] _(non-blocking)_ Should the deep dive have a maximum question count? The plan lets the planner
      decide the list length. If interviews run long, cap `probePlanSchema.questions` with `.max(n)` —
      a one-line change in `packages/core`.

---

## Verification plan

Acceptance criteria for the QA step, each independently checkable:

1. `pnpm install && pnpm typecheck && pnpm test` all pass from a clean clone.
2. `pnpm db:generate` produces no diff when run twice — the committed migration matches the schema.
3. With valid credentials, `pnpm dev` starts both processes; joining from the browser causes the
   agent to join and greet within a few seconds.
4. The agent asks for **name and age first**, and does not ask about a job until both are captured.
5. The agent asks for **job title and job description second**, and does not begin the deep dive
   until both are captured.
6. Answering "I'm a software engineer working in C# and .NET" produces deep-dive questions that
   explicitly reference C#/.NET — and answering with an unrelated profession (e.g. "I'm a chef")
   produces questions about _that_ profession, with no code in them. Both cases must pass; the
   second is what proves F3 was met rather than a C# prompt hardcoded.
7. `session.run()` unit tests cover: identity extraction, role extraction, out-of-order recording
   rejection, static-planner fallback, and deep-dive walking of a two-question stub plan.
8. After a completed interview, `interviews` has exactly one row with `status='completed'`, both
   name and age, both role fields, and `deep_dive_turns` has one ordered row per probe question.
9. Killing the agent worker mid-interview leaves `status='in_progress'` with the already-answered
   topics persisted — nothing completed is lost.
10. The browser progress panel reflects each topic's completion during the call, and
    `/interviews/<id>` after it shows the same values read from SQLite.
11. No API key appears in any committed file; `.env` is gitignored and `.env.example` has empty
    values.

---

## Verification gate <!-- Phase 8 -->

**Mechanical pass:** clean.

- Context section carries `path:line` anchors for every module touched (framework anchors, since
  the repo is empty) — non-zero.
- Every numbered step contains a `Verify:`.
- No empty table cells.
- Every pattern row has a force plus both prior art and a rejected alternative.
- No extension-point justification contains "might", "in case", "later", or "future-proof" — each
  of the three names a decision already made in this session or an implementation written in this
  plan.
- Data/migrations section is non-empty.
- Hard constraints section is non-empty.
- Tier recorded as structural; all phases were run.

**Structural-tier check-in:** the skill requires a blocking check-in before the plan file is
written. It was taken **before** planning began, as three direct questions to the user, which fixed
the three decisions a structural plan turns on: full Next.js frontend (not a token-server-only
scaffold), in-memory cache plus SQLite persistence (not Postgres, not JSON files), and ElevenLabs
Scribe for STT (not Deepgram, not a swappable interface). Those answers are load-bearing throughout
this plan and are called out again in the handover.

**Cold reader flagged**, and what changed as a result:

1. _"Which file is the worker entry — `main.ts` or `interviewer.ts`? `import.meta.filename` in the
   `cli.d.ts` example points at itself."_ → Step 3 now states explicitly that `interviewer.ts`
   holds the default export and `main.ts` passes its path, resolved explicitly rather than via
   `import.meta.filename`.
2. _"Is Silero VAD a dependency or not? It is listed in Orientation but the Approach omits it."_ →
   Maintainability and Step 3 now say: start with the session's auto-provisioned bundled VAD, add
   the plugin only if that fails, and record the outcome.
3. _"Why does `ProbePlanner` get an interface when the rules forbid speculative extension points?"_
   → The extension table now states that both implementations are written in this plan and that the
   stub is what Step 6's test runs against.
4. _"What proves topic 3 is genuinely adaptive rather than a C#-flavoured prompt?"_ → Acceptance
   criterion 6 now requires a **non-technical** profession to produce non-technical questions.
5. _"Two processes open one SQLite file — who writes?"_ → Added to Risks: WAL, agent writes,
   `apps/web` is read-only by design.
6. _"`age` from speech will be messy — where is that handled?"_ → Added to Risks, resolved by the
   zod range on the tool schema causing a natural re-ask.

Both passes were re-run after these fixes and are clean.

---

## Outcome

**Deviations from the plan:** One mechanism-level deviation, design unchanged: `defineAgent`'s
`onSessionEnd` decides completed-vs-abandoned via a module-scoped closure (`activeInterview` in
`interviewer.ts`) rather than through `ctx.userData` as the plan's Step 8 wording implied —
`JobContext` has no per-job custom-data field (only `JobProcess.userData`, which is process-wide
pre-warm state shared across jobs, not this job's interview state). Safe because a job process
runs one job's `entry`/`onSessionEnd` pair at a time. Everything else matches the plan's Design as
written; see each step's Progress entry for the smaller absorbed corrections (git repo scoping in
Step 1, env/path resolution in Steps 7/9/10, the `ctx.session.currentAgent` refactor in Step 10).

**Plan defects:** None in the Design itself. Three things the plan could not have anticipated
without running the exact toolchain: (1) Turbopack does not perform TypeScript's
`.js`-specifier-resolves-to-`.ts`-file remapping for a workspace package's own relative imports,
which `tsc`, `tsx`, and Vite/Vitest all handle transparently — this forced `@interview/core`/
`@interview/db` to build to real `dist/*.js` and forced `.env` loading in `apps/web` into
`next.config.ts` instead of a route handler (both are one-time build-pipeline fixes, documented in
Step 10's Progress entry, not design changes). (2) `pnpm --filter <pkg> <script>` runs with cwd set
to that package's own directory, not the repo root — every `dotenv.config()` call and every
relative `DATABASE_URL` needed to be anchored on `import.meta.url` rather than `process.cwd()`,
found and fixed across Steps 1, 7, and 9. (3) Next evaluates every route module during `next
build`'s page-data-collection phase, even ones that don't render the data in question — a DB client
that opens its file without first creating the parent directory (as `apps/web/lib/db.ts` initially
did) takes down the _entire_ build the first time someone clones the repo and runs `pnpm run build`
before `pnpm db:migrate`, not just the one route that needed it. Fixed to mirror
`packages/db/src/migrate.ts`'s own `mkdirSync` call.

**Steps not fully verified:** Steps 3, 4, 8, 9, and 10 each have one thing that can only be checked
against a _live_ LiveKit server plus real ElevenLabs and OpenRouter API keys — none of which exist
in this environment: actually joining a room, hearing the agent speak, confirming explicit dispatch
end-to-end, watching the progress panel and transcript update live, and running a full voice
interview start-to-finish. Every one of those steps has everything _else_ it names verified for
real (not mocked) — model construction, worker boot, DB writes at every stage including a
simulated mid-interview kill, token minting with the correct `RoomAgentDispatch` payload, page and
API rendering against seeded data. Closing them requires the user to fill in `.env` from
`.env.example` and run `pnpm dev`, then join from the browser at `http://localhost:3000`.

**Left behind:** No code left dead per the plan's Maintainability section (there was none to
delete — greenfield). Known, disclosed gaps: `OpenRouterProbePlanner`'s own retry-then-fallback
code path is exercised only through its interface contract in tests (the stub planner), not against
a real or a deliberately-failing OpenRouter call — the plan's own Step 6 verify text didn't ask for
that, but a future hardening pass should add it. Editing `packages/core` or `packages/db` source
requires an explicit rebuild (`pnpm build:libs`) before `apps/web` or a `tsx`-run `packages/agent`
will see the change — a normal monorepo tradeoff once packages are consumed as compiled output
rather than live source, and one a follow-up plan could remove with a `tsc --watch` in `pnpm dev`.
No default `OPENROUTER_MODEL` is chosen in `.env.example` — deliberately, per the plan's own
non-blocking open question; the user (or a follow-up) should pick one with solid function-calling
support before a real run.

**For the next plan in this area:** Read this Outcome's two toolchain findings before touching
`apps/web`'s build — they are Turbopack-and-workspace-specific, not obvious from the framework docs
alone, and will resurface for any new workspace package the web app starts importing at runtime
(not just types). If adding a fourth interview topic or changing the deep-dive's per-turn
persistence granularity (currently: the whole deep dive is written to the DB only when topic 3
completes, not question-by-question — see `persistence.ts`'s doc comment), that is a design change,
not an extension of the current write-through mechanism.

## Progress

- [x] 1. Workspace skeleton — `verified`: `pnpm install` completed and `pnpm -r exec node -e "console.log(1)"` printed `1` for all 4 packages. Correction: pnpm's default `dangerouslyAllowAllBuilds` policy blocked postinstall scripts for `@livekit/local-inference`, `better-sqlite3`, and `esbuild`; approved them via `allowBuilds: true` in `pnpm-workspace.yaml` (all three are required — Silero VAD's native inference, better-sqlite3's driver, and esbuild/tsx's runtime). Also found `.git` was initialized at the home directory (`/home/bashmohandes-abdallah/.git`), not this project folder — re-initialized a repo scoped to `Nancy-ai/LiveKit` before writing any files, since committing under the home-level repo would have risked staging `.ssh/`, `.gnupg/`, and other unrelated home-directory content.
- [x] 2. `packages/core` — domain types and schemas — `verified`: `pnpm --filter @interview/core test` → 10/10 passing (out-of-order recording throws, deep-copy snapshot, onChange fires once per mutation and honors unsubscribe). `tsc --noEmit` clean.
- [x] 3. Agent worker connects and speaks — `blocked` (partial): everything verifiable without live third-party credentials passed. `tsc --noEmit` clean. `config.ts` fails loudly and lists every missing env var when unset. `createModels()` constructs the ElevenLabs STT (`scribe_v2_realtime`), ElevenLabs TTS (`eleven_flash_v2_5`), and OpenRouter-pointed OpenAI-compatible LLM with no network call (confirmed after calling the framework's `initializeLogger`, which `cli.runApp` itself calls before importing the agent file — matches real startup order). `pnpm exec tsx src/main.ts dev` with placeholder credentials boots the worker fully — "starting worker", inference runner init, "Server is listening" — and only fails at the LiveKit websocket handshake (`401`) because the URL/keys are fake, proving `main.ts` → `interviewer.ts` → `models.ts` → `config.ts` all resolve and construct correctly, and confirming the plan's `execArgv` inheritance assumption for forking `.ts` job processes under tsx. **What is blocked and why:** actually joining a room and hearing the agent speak requires real `LIVEKIT_URL`/`LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET`, `ELEVENLABS_API_KEY`/`ELEVEN_VOICE_ID`, and `OPENROUTER_API_KEY`/`OPENROUTER_MODEL` — none of which exist in this environment. Closed by the user running `pnpm dev:agent` with real credentials in `.env` and joining via the LiveKit Agents Playground or `lk room join`. VAD: not evaluated (requires a live room); started on the bundled auto-provisioned Silero VAD per plan, `@livekit/agents-plugin-silero` not added.
- [x] 4. Explicit dispatch wiring — `verified`: `main.ts` now passes `agentName: config.LIVEKIT_AGENT_NAME` explicitly; a direct `new ServerOptions({agent, agentName: 'interviewer'})` check confirms `opts.agentName === 'interviewer'` and `opts.agentNameIsEnv === false` (explicitly set, not the framework's own env fallback). Worker still boots cleanly with placeholder credentials. Verifying that a room _without_ a dispatch gets no agent and one _with_ `RoomAgentDispatch({agentName:'interviewer'})` does requires a live LiveKit server — deferred to Step 9, where the token route constructs exactly that `RoomAgentDispatch` and an end-to-end join is the observable.
- [x] 5. Topics 1 and 2 as `AgentTask`s — `verified`: `pnpm --filter @interview/agent test` — a real `LLM`/`LLMStream` subclass (`StubLLM`, no network) drives `AgentSession.run({userInput: "I'm Sam, twenty nine"})` against a harness agent running `IdentityTask` exactly as the orchestrator will; `record_identity` fires with `{fullName:'Sam', age:29}` (asserted via the recorded `function_call` event) and `IdentityTask.run()` resolves that same typed value back to the caller. `tsc --noEmit` clean. Confirmed 5/5 repeat runs, no flakiness. Finding worth flagging: `RunResult.wait()` and `session.waitForIdle()` only cover the run's own speech handle/activity queue, not a caller _outside_ the run (e.g. an orchestrator's `onEnter`) reacting to an `AgentTask` completing — that reaction is real but has no session-observable event, so the test polls for it (`test-support/wait-until.ts`) rather than asserting immediately after `wait()`. This will matter again for the deep-dive and orchestrator tests in Step 6. `RoleTask` was written and typechecks but is exercised only indirectly (no test yet — deferred to Step 6, where it runs as part of the full two-topic orchestrator flow). `interviewer.ts` intentionally left on the Step 3 `GreeterAgent` placeholder — the plan wires `InterviewOrchestrator` in at Step 8, alongside persistence.
- [x] 6. Probe planner and deep-dive task — `verified`: `pnpm --filter @interview/core test` — 15/15, including `StaticProbePlanner` producing questions naming "C#" and ".NET" for a technical role and domain-grounded, code-free questions for "Chef" (proves adaptivity, not a hardcoded C# prompt). `pnpm --filter @interview/agent test` — 3/3 (`IdentityTask`, `DeepDiveTask` walking two scripted questions to completion with both turns landing in the resolved `DeepDiveAnswer`, and a full `InterviewOrchestrator` run sequencing identity → role → deep dive with a stub `ProbePlanner`, asserting `state.role`/`state.deepDive` are still `null` at each intermediate point and `status === 'completed'` only at the end). `tsc --noEmit` clean in both packages. 5/5 repeat runs of the agent suite, no flakiness. `OpenRouterProbePlanner` (the real, network-calling implementation) typechecks but is exercised only through its interface contract via the stub in tests — its actual OpenRouter call, retry, and fallback-on-second-failure path are not exercised against a live endpoint; closed by Step 9/10's live interview.
- [x] 7. `packages/db` — schema, migrations, repository — `verified`: `pnpm db:generate` (run from repo root) produced `packages/db/drizzle/0000_init_interviews.sql` matching the plan's Data/migrations spec exactly (3 tables, both FKs `ON DELETE cascade`, both unique `(interview_id, seq)` indexes, `interviews_room_name_idx`); regenerating produces "No schema changes, nothing to migrate" (idempotent, acceptance criterion 2). `pnpm db:migrate` applied it to a real file at `data/interviews.db` (verified via `sqlite3 .schema`). `pnpm --filter @interview/db test` — 4/4 (full round-trip through every repository function including `getInterview`, `null` for an unknown id, `abandonInterview` leaving `completedAt` null, and cascade-delete of `deep_dive_turns`). `tsc --noEmit` clean. **Correction, not a plan defect:** `pnpm --filter <pkg> <script>` runs with cwd set to that package's directory, not the repo root — a bare `import 'dotenv/config'` and a bare relative `DATABASE_URL` both silently resolved per-package (a first migrate attempt landed the db file at `packages/db/data/` instead of the repo-root `data/` the plan and `.env.example` intend). Fixed by anchoring `.env` loading and `DATABASE_URL` resolution on the repo root via `import.meta.url` in `packages/db/src/env.ts` and `packages/agent/src/config.ts`, rather than `process.cwd()`. This same fix will matter for Step 9's Next.js API routes if they read `.env` directly.
- [x] 8. Wire persistence into the agent — `verified`: `pnpm --filter @interview/agent test` — 4/4, including a new integration test (`persistence.test.ts`) that runs the real `InterviewOrchestrator` + real `wireStatePersistence`/`wireTranscriptPersistence` against a real (in-memory, migrated) SQLite database — no room, no mocks of the DB layer. It confirms: after topics 1–2 complete but before the deep dive finishes, `getInterview` already shows `status: 'in_progress'`, the identity/role fields, `completedAt: null`, and an empty `deepDiveTurns` (simulating "kill the worker mid-interview" from the plan's Steps and Risks); after the deep dive finishes, `status` flips to `completed`, `completedAt` is set, `deepDiveTurns` and `deepDiveSummary` are populated; and `transcript_turns` received both agent and user rows via `conversation_item_added`. `tsc --noEmit` clean in `agent` and `db`. Worker still boots cleanly end-to-end with the full DB/planner/orchestrator wiring in place (placeholder credentials, same expected 401-at-handshake failure point as Steps 3/4 — the import chain itself resolves correctly). 5/5 repeat runs, no flakiness.

  **Deviation from the plan's literal wording (absorbed, does not change the Design):** the plan's Step 8 text said to add `onSessionEnd` to `defineAgent` "that calls completeInterview or abandonInterview depending on `userData.status`" — but `JobContext` (the only argument `onSessionEnd` receives, per `dist/generator.d.ts`) has no per-job `userData` field; `JobProcess.userData` (`dist/job.d.ts:145`) is process-wide pre-warm state shared across jobs, not this job's interview state. Implemented the same intent — `onSessionEnd` decides completed-vs-abandoned from the interview's own status — via a module-scoped closure variable (`activeInterview`) set in `entry()` and read in `onSessionEnd()`, safe because a job process runs one job's `entry`/`onSessionEnd` pair at a time. The mechanism changed; the design (framework's own session-end lifecycle hook decides completed vs. abandoned) did not.

  **Correction, not a plan defect:** `packages/db`'s flat `export * from './schema.js'` re-exports each table individually but not as a `schema` namespace object, which `drizzle(sqlite, { schema })` needs; added `export * as schema from './schema.js'` alongside it (both now exported; used by the new integration test and available to `apps/web` in Step 9).

  **What remains blocked, same as Steps 3–4:** actually joining a live room, running a full voice interview, and confirming the on-disk `data/interviews.db` after a real call — requires live LiveKit/ElevenLabs/OpenRouter credentials not present in this environment. Everything else the plan's Step 8 verify describes is now proven against real (non-mocked) persistence.

- [x] 9. `apps/web` — token route and room — `verified`: `pnpm --filter @interview/web exec next build` (Turbopack) compiles cleanly and generates all 4 routes (`/`, `/_not-found`, `/api/token`, `/room/[roomName]`). Ran `next dev` and hit all three live: `GET /` → 200, contains "Start interview"; `GET /room/test-room-1?name=Sam` → 200, contains "Connecting…" (the client-side token fetch placeholder, expected without a live LiveKit server); `POST /api/token {roomName, participantName}` → 200 with a decodable JWT whose `video` grant is `{room, roomJoin: true, canPublish: true, canSubscribe: true}` and whose `roomConfig.agents` is `[{agentName: 'interviewer', ...}]` — the explicit-dispatch payload Step 4's `agentName` wiring depends on, now proven end-to-end from token mint to JWT claim. `tsc --noEmit` clean.

  **Correction, not a plan defect:** the plan's env-loading pattern (root-anchored `dotenv.config()` via `import.meta.url`, established in Step 7) does not work inside a Next.js/Turbopack route handler — Turbopack statically analyzes `new URL(..., import.meta.url)` for its module graph and failed the build with "Module not found" on a relative path that walks outside the app directory, even though the identical pattern is fine in plain Node (`tsx`) in `packages/agent` and `packages/db`. Fixed by loading `.env` in `next.config.ts` instead (loaded directly by the Next CLI in plain Node, before Turbopack ever runs, and before any request is handled) rather than in the route handler, which now reads `process.env` directly.

  **What remains blocked:** actually joining the room from the browser and hearing the agent requires a live LiveKit server plus real ElevenLabs/OpenRouter credentials — same gap as Steps 3/4/8. Everything else Step 9 names (token minting, explicit dispatch payload, page rendering) is verified.

- [x] 10. Progress + transcript UI, and the results view — `verified`: full workspace `pnpm run build` (Turbopack) succeeds cleanly from a fully clean state (`packages/*/dist`, `apps/web/.next` removed) and generates all 6 routes (`/`, `/_not-found`, `/api/interviews/[id]`, `/api/token`, `/interviews/[id]`, `/room/[roomName]`). Seeded a real completed interview through the actual repository (`createDb`/`createInterviewRepository` against `data/interviews.db`) and hit it live: `GET /interviews/<id>` → 200, page renders the seeded name, job title, job description, and deep-dive Q&A; `GET /api/interviews/<id>` → 200 with the full JSON record; both → 404 for an unknown id, correctly. `pnpm run typecheck` and `pnpm run test` (all 4 packages, 23 tests total) pass cleanly workspace-wide, and `pnpm run lint` / `pnpm exec prettier --check` are clean on every file this plan authored. Confirmed via code reading that `ProgressPanel` and `TranscriptPanel` are wired into `InterviewRoom` and use the documented `registerTextStreamHandler`/`useTranscriptions` APIs; actually seeing them update live requires a real room, which is blocked the same way as Steps 3/4/8/9.

  **Structural corrections discovered while making this step actually build (not scope changes — the design is unchanged; these are the fixes needed to make Turbopack's bundler agree with the same source layout tsc/tsx already accepted):**
  1. **`@interview/core` and `@interview/db` now build to real `dist/*.js`**, and their `package.json` `main`/`types` point there instead of `src/index.ts`. Turbopack (unlike `tsc`/`tsx`/Vite/Vitest) does not perform TypeScript's `.js`-specifier-resolves-to-`.ts`-file remapping for a workspace package's own internal relative imports — `apps/web`'s build failed with "Module not found: Can't resolve './schema.js'" pointing at `packages/db/src/index.ts`'s own `export * from './schema.js'` line. Root `dev` and `build` scripts now run a `build:libs` step (`tsc -p` for `core` then `db`) before touching `apps/web` or `packages/agent`; `typecheck` runs it too, plus `next typegen` (for the `RouteContext` global type used in the interviews API route). Each package's `tsconfig.json` now excludes `*.test.ts` from its build output, so `dist` never carries a stray test file that a later `pnpm -r test` could double-count.
  2. **A route handler cannot resolve a relative `.env` path via `import.meta.url`.** The token route's `new URL('../../../../../', import.meta.url)` (an extension of the pattern already used successfully in `packages/agent`/`packages/db`, which are plain Node/tsx, not bundled) made Turbopack fail the build the same way, since it statically analyzes that construct for its module graph. Moved `.env` loading into `next.config.ts` (read directly by the Next CLI in plain Node, before Turbopack runs) and, while there, resolved `DATABASE_URL` to an absolute path once and wrote it back into `process.env`, so `apps/web/lib/db.ts` (Step 10's read-only DB access for the results view) never needs its own path trick either.
  3. **Three-way lint conflict removed by design, not suppression.** The `let self: <Task>; super(...); self = this;` closure pattern from Steps 5–6 tripped both `prefer-const` and `@typescript-eslint/no-this-alias` at every one of its three call sites. Refactored `createCompletionTool` and `DeepDiveTask`'s tool to reach the currently-active task via `ctx.session.currentAgent` (a real, documented `AgentSession` getter, `dist/voice/agent_session.d.ts:535`) instead of a pre-assigned closure variable — removes the aliasing entirely rather than adding `eslint-disable` comments, and is one line shorter at each of the three sites. Re-verified all agent tests still pass after the refactor (same 4/4).
  4. `apps/web`'s `test` script now passes `--passWithNoTests` (vitest 5 exits non-zero on an empty suite by default; this package has no test files of its own yet, which is expected — its logic lives in `packages/core`/`packages/db`/`packages/agent`, which do).
  5. **A production build from a genuinely clean clone (no `data/` directory yet) crashed entirely**, not just the one route: `apps/web/lib/db.ts` opened the SQLite file at module-evaluation time without first creating its parent directory (unlike `packages/db/src/migrate.ts`, which already does this), and Next's page-data-collection phase evaluates every route module — including static ones like `/` — during `next build`, so one missing directory took down the whole build with a raw "directory does not exist" error. Fixed by calling the same `mkdirSync(dir, {recursive: true})` `migrate.ts` uses, in `lib/db.ts`, before `createDb()`. Re-verified: a full clean build (`rm -rf packages/*/dist apps/web/.next data && pnpm run build`) now succeeds with no `data/` directory pre-created, and hitting `/api/interviews/:id` against that fresh, unmigrated file now degrades to a normal request-scoped `500` instead of crashing anything.

  **What remains blocked, same as Steps 3/4/8/9:** a live end-to-end interview (join → live progress panel updates → live transcript → post-call results matching) needs real LiveKit/ElevenLabs/OpenRouter credentials, not present in this environment.
