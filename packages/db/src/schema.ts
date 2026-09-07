import { index, integer, sqliteTable, text, uniqueIndex } from 'drizzle-orm/sqlite-core';

/**
 * One row per interview. Topic 1 and topic 2 answers are columns (fixed, typed, known in
 * advance); only the deep dive — whose length depends on the adaptive probe plan — gets its own
 * table (plan Data/migrations: "Topic answers are stored as columns... because the three topics
 * are fixed and typed; only the deep dive... gets its own table").
 */
export const interviews = sqliteTable(
  'interviews',
  {
    id: text('id').primaryKey(),
    roomName: text('room_name').notNull(),
    participantIdentity: text('participant_identity'),
    /** 'in_progress' | 'completed' | 'abandoned' */
    status: text('status').notNull().default('in_progress'),
    fullName: text('full_name'),
    age: integer('age'),
    jobTitle: text('job_title'),
    jobDescription: text('job_description'),
    domain: text('domain'),
    seniority: text('seniority'),
    /** JSON-encoded string[] */
    technologies: text('technologies'),
    /** JSON-encoded ProbePlan */
    probePlan: text('probe_plan'),
    deepDiveSummary: text('deep_dive_summary'),
    startedAt: integer('started_at').notNull(),
    updatedAt: integer('updated_at').notNull(),
    completedAt: integer('completed_at'),
  },
  (table) => [index('interviews_room_name_idx').on(table.roomName)],
);

export const deepDiveTurns = sqliteTable(
  'deep_dive_turns',
  {
    id: integer('id').primaryKey({ autoIncrement: true }),
    interviewId: text('interview_id')
      .notNull()
      .references(() => interviews.id, { onDelete: 'cascade' }),
    seq: integer('seq').notNull(),
    question: text('question').notNull(),
    answer: text('answer').notNull(),
    createdAt: integer('created_at').notNull(),
  },
  (table) => [uniqueIndex('deep_dive_turns_interview_seq_idx').on(table.interviewId, table.seq)],
);

export const transcriptTurns = sqliteTable(
  'transcript_turns',
  {
    id: integer('id').primaryKey({ autoIncrement: true }),
    interviewId: text('interview_id')
      .notNull()
      .references(() => interviews.id, { onDelete: 'cascade' }),
    seq: integer('seq').notNull(),
    /** 'user' | 'agent' */
    role: text('role').notNull(),
    text: text('text').notNull(),
    createdAt: integer('created_at').notNull(),
  },
  (table) => [uniqueIndex('transcript_turns_interview_seq_idx').on(table.interviewId, table.seq)],
);
