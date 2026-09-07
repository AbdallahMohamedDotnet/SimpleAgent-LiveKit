import OpenAI from 'openai';
import {
  probePlanSchema,
  probePlanSystemPrompt,
  StaticProbePlanner,
  type ProbePlan,
  type ProbePlanner,
  type RoleAnswer,
} from '@interview/core';

export interface OpenRouterProbePlannerOptions {
  apiKey: string;
  model: string;
  baseURL?: string;
  /**
   * Total wall-clock budget for planning, across both attempts. Once it is spent the static
   * planner answers immediately. This is a latency guarantee, not a network timeout: topic 3
   * must start within a bounded time of topic 2 ending, however slowly OpenRouter is behaving.
   */
  timeoutMs?: number;
  client?: OpenAI;
}

const DEFAULT_TIMEOUT_MS = 6000;
/** Enough for a 5-question plan with headroom; a smaller cap makes truncation, not speed. */
const MAX_TOKENS = 500;

/**
 * Turns a `RoleAnswer` into an adaptive `ProbePlan` via one non-conversational OpenRouter call
 * (plan Design > Patterns, "Deciding topic 3 depends on topic 2"). Validates the response with
 * `probePlanSchema`, retries once *if the budget allows*, and falls back to the deterministic
 * `StaticProbePlanner` otherwise — topic 3 degrades in quality rather than breaking the interview
 * outright (plan Risks: "Structured JSON from a non-OpenAI model may not honour response_format").
 *
 * The budget is what keeps this off the critical path. The original version issued two
 * back-to-back requests with no deadline, so a stalled provider turned the gap between topic 2 and
 * topic 3 into an unbounded silence with the participant sitting there; now the worst case is
 * `timeoutMs`, after which the static plan is used.
 */
export class OpenRouterProbePlanner implements ProbePlanner {
  #client: OpenAI;
  #model: string;
  #timeoutMs: number;
  #fallback = new StaticProbePlanner();

  constructor(opts: OpenRouterProbePlannerOptions) {
    this.#client =
      opts.client ??
      new OpenAI({
        apiKey: opts.apiKey,
        baseURL: opts.baseURL ?? 'https://openrouter.ai/api/v1',
        // The SDK's own retries would multiply the wall-clock cost of a slow provider; the
        // budgeted retry below is the only one we want.
        maxRetries: 0,
      });
    this.#model = opts.model;
    this.#timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  }

  async plan(role: RoleAnswer): Promise<ProbePlan> {
    const deadline = Date.now() + this.#timeoutMs;
    const expired = Symbol('probe-planner-deadline');
    // The budget is enforced here rather than left to the client's own `timeout`, because a
    // request that never settles at all — a half-open socket, a provider holding the connection —
    // would otherwise sit past the deadline with the participant listening to silence. The
    // per-request timeout below is still passed so a timed-out call is actually cancelled.
    let timer: NodeJS.Timeout | undefined;
    const budget = new Promise<typeof expired>((resolve) => {
      timer = setTimeout(() => resolve(expired), this.#timeoutMs);
      timer.unref?.();
    });

    try {
      for (let attempt = 0; attempt < 2; attempt++) {
        const remaining = deadline - Date.now();
        // A second attempt is only worth starting if there is time for it to plausibly finish.
        if (remaining <= (attempt === 0 ? 0 : this.#timeoutMs / 4)) break;
        try {
          const raw = await Promise.race([this.#requestPlan(role, remaining), budget]);
          if (raw === expired) break;
          return probePlanSchema.parse(raw);
        } catch {
          // Retry (loop) while budget remains, then fall through to the static planner below.
        }
      }
    } finally {
      clearTimeout(timer);
    }
    return this.#fallback.plan(role);
  }

  async #requestPlan(role: RoleAnswer, timeoutMs: number): Promise<unknown> {
    const completion = await this.#client.chat.completions.create(
      {
        model: this.#model,
        response_format: { type: 'json_object' },
        max_tokens: MAX_TOKENS,
        temperature: 0.5,
        messages: [
          { role: 'system', content: probePlanSystemPrompt() },
          { role: 'user', content: JSON.stringify(role) },
        ],
      },
      { timeout: timeoutMs },
    );
    const content = completion.choices[0]?.message?.content;
    if (!content) throw new Error('OpenRouter planner returned an empty response');
    return JSON.parse(content);
  }
}
