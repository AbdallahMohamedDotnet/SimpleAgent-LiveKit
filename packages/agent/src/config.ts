import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import dotenv from 'dotenv';
import { z } from 'zod';

// Anchored on the repo root (packages/agent/src/config.ts -> ../../../) rather than
// `process.cwd()`, because `pnpm --filter @interview/agent <script>` runs with cwd set to this
// package's own directory, not the repo root where the one shared `.env` lives.
const repoRoot = fileURLToPath(new URL('../../../', import.meta.url));
dotenv.config({ path: resolve(repoRoot, '.env') });

/** Parses an optional numeric env var, falling back to `fallback` when unset or blank. */
const numeric = (fallback: number) =>
  z.preprocess(
    (v) => (v === undefined || v === '' ? fallback : Number(v)),
    z.number().refine(Number.isFinite, 'must be a number'),
  );

/** Parses an optional boolean-ish env var (`true`/`1`/`yes` are true). */
const boolean = (fallback: boolean) =>
  z
    .string()
    .optional()
    .transform((v) => (v === undefined || v === '' ? fallback : /^(1|true|yes|on)$/i.test(v)));

/**
 * Environment contract for the agent worker. Validated once, at import time, so a missing or
 * malformed key fails the worker at boot with a clear message rather than surfacing later as a
 * silent dead room (see plan Design > Patterns, "Provider failure handling").
 *
 * Everything below `DATABASE_URL` is a latency knob. They all have defaults tuned for a
 * responsive voice loop, so an existing `.env` keeps working unchanged — they exist so the
 * responsiveness/accuracy trade-off can be moved without a code change.
 */
const envSchema = z.object({
  LIVEKIT_URL: z.string().min(1, 'LIVEKIT_URL is required'),
  LIVEKIT_API_KEY: z.string().min(1, 'LIVEKIT_API_KEY is required'),
  LIVEKIT_API_SECRET: z.string().min(1, 'LIVEKIT_API_SECRET is required'),
  LIVEKIT_AGENT_NAME: z.string().min(1).default('interviewer'),
  ELEVENLABS_API_KEY: z.string().min(1, 'ELEVENLABS_API_KEY is required'),
  ELEVEN_VOICE_ID: z.string().min(1, 'ELEVEN_VOICE_ID is required'),
  OPENROUTER_API_KEY: z.string().min(1, 'OPENROUTER_API_KEY is required'),
  OPENROUTER_MODEL: z.string().min(1, 'OPENROUTER_MODEL is required'),
  DATABASE_URL: z.string().min(1).default('./data/interviews.db'),

  /**
   * End-of-turn detection strategy.
   *
   * - `v1-mini` (default) — LiveKit's turn detector running *in-process* via
   *   `@livekit/local-inference`. Chosen as the default over the SDK's own auto-selection, which
   *   prefers the cloud `v1` model: `v1` adds a round trip to the LiveKit inference gateway on
   *   every pause, and on a self-hosted server without cloud credentials it has to fail over to
   *   `v1-mini` anyway.
   * - `v1` — the cloud model. More accurate; only worth it on LiveKit Cloud.
   * - `vad` / `stt` — no semantic detector at all, purely silence- or transcript-driven. Fastest,
   *   but cuts people off mid-thought.
   */
  TURN_DETECTOR: z.enum(['v1-mini', 'v1', 'vad', 'stt']).default('v1-mini'),
  /** Silence (ms) before the agent takes the turn. The SDK default is 500. */
  ENDPOINTING_MIN_DELAY_MS: numeric(300),
  /** Hard ceiling (ms) on how long the agent waits. The SDK default is 3000. */
  ENDPOINTING_MAX_DELAY_MS: numeric(2000),
  /**
   * Run TTS speculatively, before the user's turn is confirmed. Preemptive *LLM* generation is on
   * by default in the SDK; extending it to TTS removes the synthesis round trip from the critical
   * path at the cost of some discarded ElevenLabs characters on false endpoints.
   */
  PREEMPTIVE_TTS: boolean(true),
  /** Caps how long a single agent reply can run — a runaway reply is felt as latency. */
  LLM_MAX_TOKENS: numeric(300),
  LLM_TEMPERATURE: numeric(0.4),
  /**
   * Model for the one-shot probe-plan call. Defaults to `OPENROUTER_MODEL`; point it at a small
   * fast model to shrink the pause between topic 2 and topic 3, which is the longest single
   * stretch of silence in the interview.
   */
  // Blank is treated as unset, not as an error: `.env.example` ships this key empty so the knob is
  // discoverable, and copying that file must not fail the worker at boot.
  PROBE_PLANNER_MODEL: z.preprocess(
    (v) => (v === '' ? undefined : v),
    z.string().min(1).optional(),
  ),
  /** Total budget (ms) for probe planning before falling back to the static plan. */
  PROBE_PLANNER_TIMEOUT_MS: numeric(6000),
});

export class ConfigError extends Error {
  constructor(issues: string[]) {
    super(`Invalid agent configuration:\n  - ${issues.join('\n  - ')}`);
    this.name = 'ConfigError';
  }
}

function loadConfig() {
  const result = envSchema.safeParse(process.env);
  if (!result.success) {
    const issues = result.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`);
    throw new ConfigError(issues);
  }
  return {
    ...result.data,
    // Resolved against the repo root for the same reason `.env` is loaded from there — a relative
    // DATABASE_URL must not depend on which directory a script happened to be invoked from.
    DATABASE_URL: resolve(repoRoot, result.data.DATABASE_URL),
    PROBE_PLANNER_MODEL: result.data.PROBE_PLANNER_MODEL ?? result.data.OPENROUTER_MODEL,
  };
}

export const config = loadConfig();
