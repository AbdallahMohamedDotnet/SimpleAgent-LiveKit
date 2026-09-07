import { describe, expect, it } from 'vitest';
import { Agent, AgentSession, initializeLogger } from '@livekit/agents';
import { IdentityTask } from './identity-task.js';
import { StubLLM } from './test-support/stub-llm.js';
import { waitUntil } from './test-support/wait-until.js';
import type { IdentityAnswer } from '@interview/core';

initializeLogger({ pretty: false, level: 'silent' });

/** Minimal top-level agent whose only job is to run IdentityTask as a sub-conversation and
 * capture what it resolves to — mirrors exactly how InterviewOrchestrator uses it in production
 * (await inside onEnter), which is required by AgentTask.run()'s own contract. */
class IdentityHarness extends Agent {
  result?: IdentityAnswer;
  constructor() {
    super({ instructions: 'test harness' });
  }
  override async onEnter(): Promise<void> {
    this.result = await new IdentityTask().run();
  }
}

describe('IdentityTask (via AgentSession.run, no room, no network)', () => {
  it('completes with a typed IdentityAnswer once record_identity fires', async () => {
    const llm = new StubLLM([
      {
        match: /Sam/,
        toolName: 'record_identity',
        args: { fullName: 'Sam', age: 29 },
      },
    ]);
    const harness = new IdentityHarness();
    const session = new AgentSession({ llm, vad: null });
    await session.start({ agent: harness });

    const result = await session.run({ userInput: "I'm Sam, twenty nine" });
    await result.wait();
    await session.waitForIdle();
    // `harness.result` is set by IdentityTask.run()'s continuation *inside* onEnter, which is
    // genuinely async relative to the run's own speech handle — see waitUntil's doc comment.
    await waitUntil(() => harness.result !== undefined);

    const functionCallEvent = result.events.find(
      (e) => e.type === 'function_call' && e.item.name === 'record_identity',
    );
    expect(functionCallEvent).toBeDefined();
    expect(JSON.parse((functionCallEvent as { item: { args: string } }).item.args)).toEqual({
      fullName: 'Sam',
      age: 29,
    });

    expect(harness.result).toEqual({ fullName: 'Sam', age: 29 });
  });
});
