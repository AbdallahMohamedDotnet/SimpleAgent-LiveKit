/**
 * Instructions for the topic-1 AgentTask: name and age.
 *
 * Deliberately does not greet: the orchestrator already speaks a fixed greeting before this task
 * starts, and a second model-generated greeting cost a whole extra LLM+TTS round trip before the
 * participant was asked anything.
 */
export function identityInstructions(): string {
  return [
    'You are conducting a short, friendly voice interview. The participant has just been greeted.',
    "Your only job right now is to learn the participant's full name and age.",
    'If they give only one of the two, ask for the missing one.',
    'If the age is ambiguous or clearly not a plausible human age, ask them to confirm it as a number.',
    'As soon as you have both a name and a plausible age, call the record_identity tool with them.',
    'Do not call record_identity until you have both fields.',
    SPEAKING_STYLE,
  ].join(' ');
}

/**
 * Shared across every topic prompt. This is a latency instruction as much as a tone one: the
 * agent is speaking out loud, so every extra clause is another second the participant waits
 * before it is their turn again.
 */
export const SPEAKING_STYLE =
  'You are speaking out loud: keep every turn to one or two short sentences, ask one thing at a time, and never read lists, headings, or markdown aloud.';
