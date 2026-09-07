import { describe, expect, it } from 'vitest';
import { AgentSession, initializeLogger } from '@livekit/agents';
import { InterviewSessionState, type ProbePlanner } from '@interview/core';
import { InterviewOrchestrator } from './orchestrator.js';
import { StubLLM } from './test-support/stub-llm.js';
import { waitUntil } from './test-support/wait-until.js';
import type { InterviewUserData } from './tools.js';

initializeLogger({ pretty: false, level: 'silent' });

class FixedPlanner implements ProbePlanner {
  async plan() {
    return {
      topic: 'backend software engineering',
      questions: ['What did you build recently?'],
    };
  }
}

describe('InterviewOrchestrator (via AgentSession.run, no room, no network)', () => {
  it('sequences identity -> role -> deep dive and marks the interview completed', async () => {
    const llm = new StubLLM([
      {
        match: /Sam/,
        toolName: 'record_identity',
        args: { fullName: 'Sam', age: 29 },
      },
      {
        match: /software engineer/i,
        toolName: 'record_role',
        args: {
          jobTitle: 'Software Engineer',
          jobDescription: 'Builds backend services',
          domain: 'backend software engineering',
          technologies: ['C#', '.NET'],
        },
      },
      {
        match: /caching layer/,
        toolName: 'record_probe_answer',
        args: { question: 'What did you build recently?', answer: 'A caching layer' },
      },
    ]);

    const state = new InterviewSessionState();
    const userData: InterviewUserData = { state };
    const session = new AgentSession<InterviewUserData>({ llm, vad: null, userData });
    await session.start({ agent: new InterviewOrchestrator(new FixedPlanner()) });

    // Topic 1 must be answered before topic 2 becomes reachable — assert the intermediate state
    // between turns, not just the final snapshot, so an accidental re-ordering would fail here.
    await (await session.run({ userInput: "I'm Sam, twenty nine" })).wait();
    await session.waitForIdle();
    await waitUntil(() => state.identity !== null);
    expect(state.role).toBeNull();

    await (
      await session.run({ userInput: 'I am a software engineer working in C# and .NET' })
    ).wait();
    await session.waitForIdle();
    await waitUntil(() => state.role !== null);
    expect(state.deepDive).toBeNull();

    await (await session.run({ userInput: 'I built a caching layer' })).wait();
    await session.waitForIdle();
    await waitUntil(() => state.status === 'completed');

    expect(state.identity).toEqual({ fullName: 'Sam', age: 29 });
    expect(state.role).toEqual({
      jobTitle: 'Software Engineer',
      jobDescription: 'Builds backend services',
      domain: 'backend software engineering',
      technologies: ['C#', '.NET'],
    });
    expect(state.deepDive).toEqual({
      turns: [{ question: 'What did you build recently?', answer: 'A caching layer' }],
      summary: 'What did you build recently? — A caching layer',
    });
    expect(state.status).toBe('completed');
  });
});
