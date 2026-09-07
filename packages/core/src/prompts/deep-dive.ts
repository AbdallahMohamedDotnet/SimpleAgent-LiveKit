import { SPEAKING_STYLE } from './identity.js';

/** Instructions for the topic-3 AgentTask: walk the adaptive probe plan question by question. */
export function deepDiveInstructions(topic: string, questions: readonly string[]): string {
  const numbered = questions.map((q, i) => `${i + 1}. ${q}`).join(' ');
  return [
    `You are continuing the interview, now going deeper into the participant's work in ${topic}.`,
    'Ask the following questions one at a time, in order, waiting for a real answer to each before moving on:',
    numbered,
    'You may ask a brief natural follow-up if an answer is very short or vague, but do not skip ahead and do not add extra questions beyond this list.',
    'After the participant answers a question, call the record_probe_answer tool with that exact question text and their answer.',
    // Without this, the model records the answer, waits for the tool result, and only then decides
    // what to say — two round trips per question with silence in between. The tool result already
    // contains the next question verbatim, so the model has nothing left to work out.
    'The tool result tells you the next question: ask it immediately, in the same turn, rather than pausing or acknowledging at length.',
    SPEAKING_STYLE,
  ].join(' ');
}
