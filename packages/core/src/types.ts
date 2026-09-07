import type { DeepDiveAnswer, IdentityAnswer, ProbePlan, RoleAnswer } from './schemas.js';

export type InterviewTopic = 'identity' | 'role' | 'deepDive';

export type InterviewStatus = 'in_progress' | 'completed' | 'abandoned';

/** One immutable record of an in-room transcript turn, used for the live transcript panel. */
export interface TranscriptTurn {
  role: 'user' | 'agent';
  text: string;
  createdAt: number;
}

/** The shape returned by `InterviewSessionState.snapshot()` — safe to serialize to the browser. */
export interface InterviewSnapshot {
  status: InterviewStatus;
  currentTopic: InterviewTopic | null;
  identity: IdentityAnswer | null;
  role: RoleAnswer | null;
  probePlan: ProbePlan | null;
  deepDive: DeepDiveAnswer | null;
}

/**
 * What the agent actually publishes on the `interview.progress` topic: a snapshot plus the
 * interview's id, which the browser cannot derive on its own but needs to link to the results
 * page once the call ends.
 */
export interface InterviewProgressMessage extends InterviewSnapshot {
  interviewId: string;
}
