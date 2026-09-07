import type { DeepDiveAnswer, IdentityAnswer, ProbePlan, RoleAnswer } from './schemas.js';
import type { InterviewSnapshot, InterviewStatus, InterviewTopic } from './types.js';

const TOPIC_ORDER: readonly InterviewTopic[] = ['identity', 'role', 'deepDive'];

type TopicValueMap = {
  identity: IdentityAnswer;
  role: RoleAnswer;
  deepDive: DeepDiveAnswer;
};

export type InterviewChangeListener = (snapshot: InterviewSnapshot) => void;

/**
 * The in-memory session cache the orchestrator and its tools share via `AgentSession.userData`
 * (see docs/plans/2026-09-06-livekit-interview-agent-scaffold.md, Design > Approach). Holds
 * exactly the three topic answers plus the probe plan, in strict order — this is what makes
 * "recording out of order" a programming error caught here rather than a silent data corruption
 * discovered later in SQLite.
 */
export class InterviewSessionState {
  private _status: InterviewStatus = 'in_progress';
  private _identity: IdentityAnswer | null = null;
  private _role: RoleAnswer | null = null;
  private _probePlan: ProbePlan | null = null;
  private _deepDive: DeepDiveAnswer | null = null;
  private readonly _listeners = new Set<InterviewChangeListener>();

  get status(): InterviewStatus {
    return this._status;
  }

  get identity(): IdentityAnswer | null {
    return this._identity;
  }

  get role(): RoleAnswer | null {
    return this._role;
  }

  get probePlan(): ProbePlan | null {
    return this._probePlan;
  }

  get deepDive(): DeepDiveAnswer | null {
    return this._deepDive;
  }

  /** The next topic that has not yet been recorded, or `null` once all three are done. */
  get currentTopic(): InterviewTopic | null {
    for (const topic of TOPIC_ORDER) {
      if (!this._hasTopic(topic)) return topic;
    }
    return null;
  }

  private _hasTopic(topic: InterviewTopic): boolean {
    if (topic === 'identity') return this._identity !== null;
    if (topic === 'role') return this._role !== null;
    return this._deepDive !== null;
  }

  /**
   * Records one topic's answer. Throws if called out of order — i.e. if an earlier topic has not
   * been recorded yet, or if this topic already has been. `deepDive` additionally requires the
   * probe plan to have been set via `setProbePlan` first.
   */
  record<T extends InterviewTopic>(topic: T, value: TopicValueMap[T]): void {
    const expected = this.currentTopic;
    if (expected !== topic) {
      throw new Error(
        `Cannot record topic "${topic}" out of order: expected "${expected ?? '(none — interview already complete)'}"`,
      );
    }
    if (topic === 'deepDive' && this._probePlan === null) {
      throw new Error('Cannot record "deepDive" before a probe plan has been set');
    }
    if (topic === 'identity') this._identity = value as IdentityAnswer;
    else if (topic === 'role') this._role = value as RoleAnswer;
    else this._deepDive = value as DeepDiveAnswer;
    this._notify();
  }

  /** Sets the adaptive probe plan for the deep dive. Requires `role` to already be recorded. */
  setProbePlan(plan: ProbePlan): void {
    if (this._role === null) {
      throw new Error('Cannot set a probe plan before "role" has been recorded');
    }
    if (this._probePlan !== null) {
      throw new Error('Probe plan has already been set');
    }
    this._probePlan = plan;
    this._notify();
  }

  markComplete(): void {
    if (this._deepDive === null) {
      throw new Error('Cannot mark the interview complete before "deepDive" has been recorded');
    }
    this._status = 'completed';
    this._notify();
  }

  markAbandoned(): void {
    if (this._status === 'completed') return;
    this._status = 'abandoned';
    this._notify();
  }

  /** A deep, serializable copy — safe to push to the browser or write to the database. */
  snapshot(): InterviewSnapshot {
    return {
      status: this._status,
      currentTopic: this.currentTopic,
      identity: this._identity ? { ...this._identity } : null,
      role: this._role ? { ...this._role, technologies: [...this._role.technologies] } : null,
      probePlan: this._probePlan
        ? { ...this._probePlan, questions: [...this._probePlan.questions] }
        : null,
      deepDive: this._deepDive
        ? { ...this._deepDive, turns: this._deepDive.turns.map((t) => ({ ...t })) }
        : null,
    };
  }

  /** Registers a listener fired once per successful mutation. Returns an unsubscribe function. */
  onChange(listener: InterviewChangeListener): () => void {
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  private _notify(): void {
    const snapshot = this.snapshot();
    for (const listener of this._listeners) listener(snapshot);
  }
}
