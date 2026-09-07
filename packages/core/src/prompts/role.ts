import { SPEAKING_STYLE } from './identity.js';

/** Instructions for the topic-2 AgentTask: job title and job description. */
export function roleInstructions(fullName: string): string {
  return [
    `You are continuing the interview with ${fullName}.`,
    'Now ask about their job: their job title, and a short description of what they actually do day to day.',
    'Also work out, from what they tell you, the general domain they work in (e.g. "backend software engineering",',
    '"marketing", "mechanical engineering", "teaching") and any specific technologies, tools, or methods they',
    'name (e.g. "C#", ".NET", "Figma", "Excel", "lathes"). Do not ask a separate question for domain or',
    'technologies if they are already implied by what was said — infer them, but do not invent ones they never',
    'mentioned.',
    'Once you can state a job title, a job description, a domain, and a list of technologies (which may be empty',
    'if genuinely none were mentioned), call the record_role tool with them.',
    SPEAKING_STYLE,
  ].join(' ');
}
