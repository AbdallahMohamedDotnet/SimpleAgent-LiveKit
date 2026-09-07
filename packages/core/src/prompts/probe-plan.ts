/**
 * System prompt for the one-shot, non-conversational LLM call that turns a RoleAnswer into a
 * ProbePlan (see @interview/core's ProbePlanner / packages/agent's OpenRouterProbePlanner).
 * Deliberately asks the model to reason from the given domain/technologies rather than pattern-
 * match a profession, so an unlisted job produces relevant questions instead of a generic filler.
 */
export function probePlanSystemPrompt(): string {
  return [
    'You generate a short, adaptive interview question plan from a job description.',
    'You will be given a JSON object with jobTitle, jobDescription, domain, technologies, and optionally seniority.',
    'Produce 3 to 5 open-ended follow-up questions that would let a technically curious interviewer',
    "understand this specific person's actual day-to-day work, going deeper into whatever domain",
    'and technologies were named. If technologies are listed, at least one question must reference',
    'a specific one by name. Do not ask generic questions that would fit any job — ground every',
    'question in what was actually said.',
    'Respond with ONLY a JSON object of the exact shape: {"topic": string, "questions": string[]}.',
    'No prose, no markdown, no explanation — just that JSON object.',
  ].join(' ');
}
