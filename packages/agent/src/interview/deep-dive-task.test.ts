import { describe, expect, it } from 'vitest';
import { Agent, AgentSession, initializeLogger } from '@livekit/agents';
import type { DeepDiveAnswer, ProbePlan } from '@interview/core';
import { DeepDiveTask } from './deep-dive-task.js';
import { StubLLM } from './test-support/stub-llm.js';
import { waitUntil } from './test-support/wait-until.js';

initializeLogger({ pretty: false, level: 'silent' });

class DeepDiveHarness extends Agent {
  result?: DeepDiveAnswer;
  constructor(private plan: ProbePlan) {
    super({ instructions: 'test harness' });
  }
  override async onEnter(): Promise<void> {
    this.result = await new DeepDiveTask(this.plan).run();
  }
}

describe('DeepDiveTask (via AgentSession.run, no room, no network)', () => {
  it('asks every planned question and completes once all are answered', async () => {
    const plan: ProbePlan = {
      topic: 'backend software engineering',
      questions: ['What did you build recently?', 'What was the hardest part of that?'],
    };

    // Both questions must actually be in the task's instructions — otherwise the model was never
    // told to ask the second one.
    const harnessInstructionsCheck = new DeepDiveTask(plan);
    expect(harnessInstructionsCheck.instructions).toContain('What did you build recently?');
    expect(harnessInstructionsCheck.instructions).toContain('What was the hardest part of that?');

    const llm = new StubLLM([
      {
        match: /caching layer/,
        toolName: 'record_probe_answer',
        args: { question: 'What did you build recently?', answer: 'A caching layer' },
      },
      {
        match: /race condition/,
        toolName: 'record_probe_answer',
        args: {
          question: 'What was the hardest part of that?',
          answer: 'Debugging a race condition',
        },
      },
    ]);
    const harness = new DeepDiveHarness(plan);
    const session = new AgentSession({ llm, vad: null });
    await session.start({ agent: harness });

    const firstRun = await session.run({ userInput: 'I built a caching layer' });
    await firstRun.wait();

    const secondRun = await session.run({ userInput: 'Debugging a nasty race condition' });
    await secondRun.wait();

    await session.waitForIdle();
    await waitUntil(() => harness.result !== undefined);

    expect(harness.result).toEqual({
      turns: [
        { question: 'What did you build recently?', answer: 'A caching layer' },
        { question: 'What was the hardest part of that?', answer: 'Debugging a race condition' },
      ],
      summary:
        'What did you build recently? — A caching layer | What was the hardest part of that? — Debugging a race condition',
    });
  });
});
