import { describe, expect, it } from 'vitest';
import Database from 'better-sqlite3';
import { drizzle, type BetterSQLite3Database } from 'drizzle-orm/better-sqlite3';
import { migrate } from 'drizzle-orm/better-sqlite3/migrator';
import { eq } from 'drizzle-orm';
import { fileURLToPath } from 'node:url';
import { AgentSession, initializeLogger } from '@livekit/agents';
import { createInterviewRepository, schema } from '@interview/db';
import { InterviewSessionState, type ProbePlanner } from '@interview/core';
import { InterviewOrchestrator } from './orchestrator.js';
import { StubLLM } from './test-support/stub-llm.js';
import { waitUntil } from './test-support/wait-until.js';
import { wireStatePersistence, wireTranscriptPersistence } from './persistence.js';
import type { InterviewUserData } from './tools.js';

initializeLogger({ pretty: false, level: 'silent' });

function createTestDb(): BetterSQLite3Database<typeof schema> {
  const sqlite = new Database(':memory:');
  sqlite.pragma('foreign_keys = ON');
  const db = drizzle(sqlite, { schema });
  migrate(db, {
    migrationsFolder: fileURLToPath(new URL('../../../db/drizzle', import.meta.url)),
  });
  return db;
}

class FixedPlanner implements ProbePlanner {
  async plan() {
    return { topic: 'backend software engineering', questions: ['What did you build recently?'] };
  }
}

describe('interview persistence (real SQLite, no room)', () => {
  it('write-through survives a mid-interview stop and completes fully once the interview finishes', async () => {
    const db = createTestDb();
    const repo = createInterviewRepository(db);
    const interviewId = await repo.createInterview({ roomName: 'room-x' });

    const state = new InterviewSessionState();
    wireStatePersistence(state, repo, interviewId);

    const llm = new StubLLM([
      { match: /Sam/, toolName: 'record_identity', args: { fullName: 'Sam', age: 29 } },
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

    const userData: InterviewUserData = { state };
    const session = new AgentSession<InterviewUserData>({ llm, vad: null, userData });
    wireTranscriptPersistence(session, repo, interviewId);
    await session.start({ agent: new InterviewOrchestrator(new FixedPlanner()) });

    await (await session.run({ userInput: "I'm Sam, twenty nine" })).wait();
    await session.waitForIdle();
    await waitUntil(() => state.identity !== null);

    await (
      await session.run({ userInput: 'I am a software engineer working in C# and .NET' })
    ).wait();
    await session.waitForIdle();
    await waitUntil(() => state.role !== null);

    // Simulates "kill the worker mid-interview" (plan Steps > 8, Risks): the interview should be
    // readable right now, mid-deep-dive, with everything answered so far persisted and nothing
    // marked complete.
    const midInterview = await repo.getInterview(interviewId);
    expect(midInterview).toMatchObject({
      status: 'in_progress',
      fullName: 'Sam',
      age: 29,
      jobTitle: 'Software Engineer',
      technologies: ['C#', '.NET'],
    });
    expect(midInterview!.completedAt).toBeNull();
    expect(midInterview!.deepDiveTurns).toEqual([]);

    await (await session.run({ userInput: 'I built a caching layer' })).wait();
    await session.waitForIdle();
    await waitUntil(() => state.status === 'completed');

    const finished = await repo.getInterview(interviewId);
    expect(finished!.status).toBe('completed');
    expect(finished!.completedAt).not.toBeNull();
    expect(finished!.deepDiveTurns).toEqual([
      { seq: 0, question: 'What did you build recently?', answer: 'A caching layer' },
    ]);
    expect(finished!.deepDiveSummary).toBe('What did you build recently? — A caching layer');

    // Transcript persistence: every chat message added during the run should have landed too.
    const transcriptRows = await db
      .select()
      .from(schema.transcriptTurns)
      .where(eq(schema.transcriptTurns.interviewId, interviewId));
    expect(transcriptRows.length).toBeGreaterThan(0);
    expect(transcriptRows.some((row) => row.role === 'agent')).toBe(true);
    expect(transcriptRows.some((row) => row.role === 'user')).toBe(true);
  });
});
