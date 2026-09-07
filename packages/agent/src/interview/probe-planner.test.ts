import { describe, expect, it, vi } from 'vitest';
import type OpenAI from 'openai';
import { OpenRouterProbePlanner } from './probe-planner.js';
import type { RoleAnswer } from '@interview/core';

const ROLE: RoleAnswer = {
  jobTitle: 'Backend engineer',
  jobDescription: 'Builds payment APIs',
  domain: 'backend software engineering',
  technologies: ['TypeScript', 'PostgreSQL'],
};

/** A stand-in for the OpenAI client, so nothing here touches the network. */
function stubClient(create: (body: unknown, opts: unknown) => Promise<unknown>): OpenAI {
  return { chat: { completions: { create } } } as unknown as OpenAI;
}

function planResponse(plan: unknown) {
  return { choices: [{ message: { content: JSON.stringify(plan) } }] };
}

describe('OpenRouterProbePlanner', () => {
  it('returns the model plan when the call succeeds', async () => {
    const client = stubClient(async () =>
      planResponse({ topic: 'payment APIs', questions: ['Tell me about PostgreSQL here.'] }),
    );
    const planner = new OpenRouterProbePlanner({ apiKey: 'k', model: 'm', client });

    await expect(planner.plan(ROLE)).resolves.toEqual({
      topic: 'payment APIs',
      questions: ['Tell me about PostgreSQL here.'],
    });
  });

  it('passes the remaining budget as the per-request timeout', async () => {
    const create = vi.fn(async () => planResponse({ topic: 't', questions: ['q'] })) as unknown as (
      body: unknown,
      opts: unknown,
    ) => Promise<unknown>;
    const planner = new OpenRouterProbePlanner({
      apiKey: 'k',
      model: 'm',
      timeoutMs: 4000,
      client: stubClient(create),
    });

    await planner.plan(ROLE);

    const [, options] = (create as unknown as { mock: { calls: [unknown, { timeout: number }][] } })
      .mock.calls[0]!;
    expect(options.timeout).toBeGreaterThan(0);
    expect(options.timeout).toBeLessThanOrEqual(4000);
  });

  it('retries once on a malformed plan, then still succeeds', async () => {
    let call = 0;
    const planner = new OpenRouterProbePlanner({
      apiKey: 'k',
      model: 'm',
      client: stubClient(async () => {
        call++;
        return call === 1
          ? planResponse({ nope: true })
          : planResponse({ topic: 't', questions: ['q'] });
      }),
    });

    await expect(planner.plan(ROLE)).resolves.toEqual({ topic: 't', questions: ['q'] });
    expect(call).toBe(2);
  });

  it('falls back to the static plan rather than exceeding its budget', async () => {
    // Never resolves within the budget — the exact failure mode the deadline exists for.
    const planner = new OpenRouterProbePlanner({
      apiKey: 'k',
      model: 'm',
      timeoutMs: 50,
      client: stubClient(() => new Promise((resolve) => setTimeout(resolve, 5000))),
    });

    const startedAt = Date.now();
    const plan = await planner.plan(ROLE);

    expect(Date.now() - startedAt).toBeLessThan(1000);
    expect(plan.questions.length).toBeGreaterThan(0);
  });
});
