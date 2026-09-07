import { randomUUID } from 'node:crypto';
import { asc, eq } from 'drizzle-orm';
import type { Db } from '../client.js';
import { deepDiveTurns, interviews, transcriptTurns } from '../schema.js';

export interface CreateInterviewInput {
  roomName: string;
  participantIdentity?: string;
}

export interface DeepDiveTurnRecord {
  seq: number;
  question: string;
  answer: string;
}

export interface InterviewRecord {
  id: string;
  roomName: string;
  participantIdentity: string | null;
  status: string;
  fullName: string | null;
  age: number | null;
  jobTitle: string | null;
  jobDescription: string | null;
  domain: string | null;
  seniority: string | null;
  technologies: string[] | null;
  probePlan: unknown | null;
  deepDiveSummary: string | null;
  startedAt: number;
  updatedAt: number;
  completedAt: number | null;
  deepDiveTurns: DeepDiveTurnRecord[];
}

/**
 * Intent-named functions over the drizzle tables — the boundary the agent and the web app both
 * go through, rather than either calling drizzle directly (plan Design > Patterns, "Persistence
 * access"). All writes are await-able, but the agent calls them fire-and-forget on each topic
 * completion (plan Design > Approach, "write-through"); nothing here blocks the speech loop.
 */
export function createInterviewRepository(db: Db) {
  async function createInterview(input: CreateInterviewInput): Promise<string> {
    // An interview with no room cannot be traced back to the call it came from, and the one way
    // to get here is reading `ctx.room.name` before `ctx.connect()` has resolved — which fails
    // silently, producing a database full of blank-roomed rows. Rejected loudly instead.
    if (input.roomName.trim().length === 0) {
      throw new Error('createInterview requires a non-empty roomName');
    }
    const id = randomUUID();
    const ts = Date.now();
    await db.insert(interviews).values({
      id,
      roomName: input.roomName,
      participantIdentity: input.participantIdentity ?? null,
      status: 'in_progress',
      startedAt: ts,
      updatedAt: ts,
    });
    return id;
  }

  async function saveIdentity(
    id: string,
    identity: { fullName: string; age: number },
  ): Promise<void> {
    await db
      .update(interviews)
      .set({ fullName: identity.fullName, age: identity.age, updatedAt: Date.now() })
      .where(eq(interviews.id, id));
  }

  async function saveRole(
    id: string,
    role: {
      jobTitle: string;
      jobDescription: string;
      domain: string;
      technologies: string[];
      seniority?: string;
    },
  ): Promise<void> {
    await db
      .update(interviews)
      .set({
        jobTitle: role.jobTitle,
        jobDescription: role.jobDescription,
        domain: role.domain,
        technologies: JSON.stringify(role.technologies),
        seniority: role.seniority ?? null,
        updatedAt: Date.now(),
      })
      .where(eq(interviews.id, id));
  }

  async function saveProbePlan(id: string, plan: unknown): Promise<void> {
    await db
      .update(interviews)
      .set({ probePlan: JSON.stringify(plan), updatedAt: Date.now() })
      .where(eq(interviews.id, id));
  }

  async function appendProbeTurn(
    id: string,
    seq: number,
    turn: { question: string; answer: string },
  ): Promise<void> {
    await db.insert(deepDiveTurns).values({
      interviewId: id,
      seq,
      question: turn.question,
      answer: turn.answer,
      createdAt: Date.now(),
    });
  }

  async function appendTranscriptTurn(
    id: string,
    seq: number,
    turn: { role: 'user' | 'agent'; text: string },
  ): Promise<void> {
    await db.insert(transcriptTurns).values({
      interviewId: id,
      seq,
      role: turn.role,
      text: turn.text,
      createdAt: Date.now(),
    });
  }

  async function completeInterview(id: string, deepDiveSummary: string): Promise<void> {
    const ts = Date.now();
    await db
      .update(interviews)
      .set({ status: 'completed', deepDiveSummary, updatedAt: ts, completedAt: ts })
      .where(eq(interviews.id, id));
  }

  async function abandonInterview(id: string): Promise<void> {
    await db
      .update(interviews)
      .set({ status: 'abandoned', updatedAt: Date.now() })
      .where(eq(interviews.id, id));
  }

  async function getInterview(id: string): Promise<InterviewRecord | null> {
    const rows = await db.select().from(interviews).where(eq(interviews.id, id));
    const row = rows[0];
    if (!row) return null;

    const turnRows = await db
      .select()
      .from(deepDiveTurns)
      .where(eq(deepDiveTurns.interviewId, id))
      .orderBy(asc(deepDiveTurns.seq));

    return {
      id: row.id,
      roomName: row.roomName,
      participantIdentity: row.participantIdentity,
      status: row.status,
      fullName: row.fullName,
      age: row.age,
      jobTitle: row.jobTitle,
      jobDescription: row.jobDescription,
      domain: row.domain,
      seniority: row.seniority,
      technologies: row.technologies ? (JSON.parse(row.technologies) as string[]) : null,
      probePlan: row.probePlan ? JSON.parse(row.probePlan) : null,
      deepDiveSummary: row.deepDiveSummary,
      startedAt: row.startedAt,
      updatedAt: row.updatedAt,
      completedAt: row.completedAt,
      deepDiveTurns: turnRows.map((t) => ({ seq: t.seq, question: t.question, answer: t.answer })),
    };
  }

  return {
    createInterview,
    saveIdentity,
    saveRole,
    saveProbePlan,
    appendProbeTurn,
    appendTranscriptTurn,
    completeInterview,
    abandonInterview,
    getInterview,
  };
}

export type InterviewRepository = ReturnType<typeof createInterviewRepository>;
