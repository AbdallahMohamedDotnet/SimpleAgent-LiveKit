import { describe, expect, it, vi } from 'vitest';
import { InterviewSessionState } from './state.js';
import type { IdentityAnswer, RoleAnswer, ProbePlan, DeepDiveAnswer } from './schemas.js';

const identity: IdentityAnswer = { fullName: 'Sam Rivera', age: 29 };
const role: RoleAnswer = {
  jobTitle: 'Software Engineer',
  jobDescription: 'Builds backend services',
  domain: 'backend software engineering',
  technologies: ['C#', '.NET'],
};
const plan: ProbePlan = { topic: 'backend software engineering', questions: ['q1', 'q2'] };
const deepDive: DeepDiveAnswer = {
  turns: [{ question: 'q1', answer: 'a1' }],
  summary: 'summary',
};

describe('InterviewSessionState', () => {
  it('starts in_progress with currentTopic identity', () => {
    const state = new InterviewSessionState();
    expect(state.status).toBe('in_progress');
    expect(state.currentTopic).toBe('identity');
  });

  it('records topics in order and advances currentTopic', () => {
    const state = new InterviewSessionState();
    state.record('identity', identity);
    expect(state.identity).toEqual(identity);
    expect(state.currentTopic).toBe('role');

    state.record('role', role);
    expect(state.role).toEqual(role);
    expect(state.currentTopic).toBe('deepDive');

    state.setProbePlan(plan);
    state.record('deepDive', deepDive);
    expect(state.deepDive).toEqual(deepDive);
    expect(state.currentTopic).toBeNull();
  });

  it('throws when recording a topic out of order', () => {
    const state = new InterviewSessionState();
    expect(() => state.record('role', role)).toThrow(/out of order/);
    expect(() => state.record('deepDive', deepDive)).toThrow(/out of order/);
  });

  it('throws when recording the same topic twice', () => {
    const state = new InterviewSessionState();
    state.record('identity', identity);
    expect(() => state.record('identity', identity)).toThrow(/out of order/);
  });

  it('throws when setting a probe plan before role is recorded', () => {
    const state = new InterviewSessionState();
    state.record('identity', identity);
    expect(() => state.setProbePlan(plan)).toThrow(/before "role"/);
  });

  it('throws when recording deepDive before a probe plan is set', () => {
    const state = new InterviewSessionState();
    state.record('identity', identity);
    state.record('role', role);
    expect(() => state.record('deepDive', deepDive)).toThrow(/probe plan/);
  });

  it('snapshot() returns a deep copy that mutation cannot affect', () => {
    const state = new InterviewSessionState();
    state.record('identity', identity);
    state.record('role', role);
    const snap = state.snapshot();
    snap.role!.technologies.push('mutated');
    expect(state.role!.technologies).toEqual(['C#', '.NET']);
  });

  it('markComplete requires deepDive to be recorded first', () => {
    const state = new InterviewSessionState();
    expect(() => state.markComplete()).toThrow(/before "deepDive"/);
    state.record('identity', identity);
    state.record('role', role);
    state.setProbePlan(plan);
    state.record('deepDive', deepDive);
    state.markComplete();
    expect(state.status).toBe('completed');
  });

  it('onChange fires exactly once per successful mutation', () => {
    const state = new InterviewSessionState();
    const listener = vi.fn();
    state.onChange(listener);
    state.record('identity', identity);
    state.record('role', role);
    state.setProbePlan(plan);
    state.record('deepDive', deepDive);
    state.markComplete();
    expect(listener).toHaveBeenCalledTimes(5);
  });

  it('unsubscribing onChange stops further notifications', () => {
    const state = new InterviewSessionState();
    const listener = vi.fn();
    const unsubscribe = state.onChange(listener);
    state.record('identity', identity);
    unsubscribe();
    state.record('role', role);
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
