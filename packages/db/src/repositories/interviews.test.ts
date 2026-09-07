import { describe, expect, it } from 'vitest';
import Database from 'better-sqlite3';
import { drizzle } from 'drizzle-orm/better-sqlite3';
import { migrate } from 'drizzle-orm/better-sqlite3/migrator';
import { fileURLToPath } from 'node:url';
import * as schema from '../schema.js';
import { createInterviewRepository } from './interviews.js';

function createTestDb() {
  const sqlite = new Database(':memory:');
  sqlite.pragma('foreign_keys = ON');
  const db = drizzle(sqlite, { schema });
  migrate(db, { migrationsFolder: fileURLToPath(new URL('../../drizzle', import.meta.url)) });
  return db;
}

describe('InterviewRepository', () => {
  it('rejects an interview with no room name', async () => {
    const repo = createInterviewRepository(createTestDb());

    // Guards the one caller mistake that produces this: reading `ctx.room.name` before
    // `ctx.connect()` resolves, which yields '' rather than throwing.
    await expect(repo.createInterview({ roomName: '' })).rejects.toThrow(/non-empty roomName/);
    await expect(repo.createInterview({ roomName: '   ' })).rejects.toThrow(/non-empty roomName/);
  });

  it('round-trips a full interview through every write and getInterview', async () => {
    const db = createTestDb();
    const repo = createInterviewRepository(db);

    const id = await repo.createInterview({ roomName: 'room-1', participantIdentity: 'sam' });

    await repo.saveIdentity(id, { fullName: 'Sam Rivera', age: 29 });
    await repo.saveRole(id, {
      jobTitle: 'Software Engineer',
      jobDescription: 'Builds backend services',
      domain: 'backend software engineering',
      technologies: ['C#', '.NET'],
    });
    const plan = { topic: 'backend software engineering', questions: ['q1', 'q2'] };
    await repo.saveProbePlan(id, plan);
    await repo.appendProbeTurn(id, 0, { question: 'q1', answer: 'a1' });
    await repo.appendProbeTurn(id, 1, { question: 'q2', answer: 'a2' });
    await repo.appendTranscriptTurn(id, 0, { role: 'agent', text: 'Hi!' });
    await repo.appendTranscriptTurn(id, 1, { role: 'user', text: "I'm Sam." });
    await repo.completeInterview(id, 'q1 — a1 | q2 — a2');

    const record = await repo.getInterview(id);
    expect(record).not.toBeNull();
    expect(record).toMatchObject({
      id,
      roomName: 'room-1',
      participantIdentity: 'sam',
      status: 'completed',
      fullName: 'Sam Rivera',
      age: 29,
      jobTitle: 'Software Engineer',
      jobDescription: 'Builds backend services',
      domain: 'backend software engineering',
      technologies: ['C#', '.NET'],
      probePlan: plan,
      deepDiveSummary: 'q1 — a1 | q2 — a2',
    });
    expect(record!.completedAt).not.toBeNull();
    expect(record!.deepDiveTurns).toEqual([
      { seq: 0, question: 'q1', answer: 'a1' },
      { seq: 1, question: 'q2', answer: 'a2' },
    ]);
  });

  it('getInterview returns null for an unknown id', async () => {
    const db = createTestDb();
    const repo = createInterviewRepository(db);
    expect(await repo.getInterview('does-not-exist')).toBeNull();
  });

  it('abandonInterview marks the interview abandoned without a completedAt', async () => {
    const db = createTestDb();
    const repo = createInterviewRepository(db);
    const id = await repo.createInterview({ roomName: 'room-2' });
    await repo.saveIdentity(id, { fullName: 'Alex', age: 40 });
    await repo.abandonInterview(id);

    const record = await repo.getInterview(id);
    expect(record!.status).toBe('abandoned');
    expect(record!.completedAt).toBeNull();
    expect(record!.fullName).toBe('Alex');
  });

  it('cascades deep dive turn deletion when the parent interview is deleted', async () => {
    const db = createTestDb();
    const repo = createInterviewRepository(db);
    const id = await repo.createInterview({ roomName: 'room-3' });
    await repo.appendProbeTurn(id, 0, { question: 'q', answer: 'a' });

    const { interviews } = schema;
    const { eq } = await import('drizzle-orm');
    await db.delete(interviews).where(eq(interviews.id, id));

    expect(await repo.getInterview(id)).toBeNull();
  });
});
