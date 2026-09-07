import type { DeepDiveTurn } from './schemas.js';

/** Deterministic, no-LLM summary of a completed deep dive — one line per question/answer pair. */
export function summarizeDeepDive(turns: readonly DeepDiveTurn[]): string {
  return turns.map((t) => `${t.question} — ${t.answer}`).join(' | ');
}
