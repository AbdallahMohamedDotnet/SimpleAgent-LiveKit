import { describe, expect, it } from 'vitest';
import { summarizeDeepDive } from './summarize.js';

describe('summarizeDeepDive', () => {
  it('joins each question/answer pair on one line', () => {
    const summary = summarizeDeepDive([
      { question: 'Q1', answer: 'A1' },
      { question: 'Q2', answer: 'A2' },
    ]);
    expect(summary).toBe('Q1 — A1 | Q2 — A2');
  });

  it('returns an empty string for no turns', () => {
    expect(summarizeDeepDive([])).toBe('');
  });
});
