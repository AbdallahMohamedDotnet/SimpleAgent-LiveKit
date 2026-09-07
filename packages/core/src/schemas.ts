import { z } from 'zod';

/**
 * Topic 1 — identity. Captured verbatim from the participant; age is constrained to a plausible
 * human range so a mis-heard number ("twenty nine" -> 29 vs a garbled 290) fails validation and
 * the agent naturally re-asks instead of silently recording nonsense.
 */
export const identityAnswerSchema = z.object({
  fullName: z.string().min(1, 'fullName must not be empty'),
  age: z.number().int().min(13).max(120),
});
export type IdentityAnswer = z.infer<typeof identityAnswerSchema>;

/**
 * Topic 2 — role. `technologies` and `domain` are what topic 3's probe planner keys off of, so
 * they are required to be informative rather than free-form padding.
 */
export const roleAnswerSchema = z.object({
  jobTitle: z.string().min(1),
  jobDescription: z.string().min(1),
  domain: z.string().min(1),
  technologies: z.array(z.string().min(1)).default([]),
  seniority: z.enum(['junior', 'mid', 'senior', 'lead', 'unspecified']).optional(),
});
export type RoleAnswer = z.infer<typeof roleAnswerSchema>;

/**
 * The adaptive question plan produced from a RoleAnswer. Kept as its own schema (rather than
 * folded into DeepDiveAnswer) so it can be logged, tested, and shown to the browser before any
 * question is actually asked.
 */
export const probePlanSchema = z.object({
  topic: z.string().min(1),
  questions: z.array(z.string().min(1)).min(1),
});
export type ProbePlan = z.infer<typeof probePlanSchema>;

/**
 * Topic 3 — the deep dive. One turn per planned question, in order, plus a short summary.
 */
export const deepDiveTurnSchema = z.object({
  question: z.string().min(1),
  answer: z.string().min(1),
});
export type DeepDiveTurn = z.infer<typeof deepDiveTurnSchema>;

export const deepDiveAnswerSchema = z.object({
  turns: z.array(deepDiveTurnSchema),
  summary: z.string().min(1),
});
export type DeepDiveAnswer = z.infer<typeof deepDiveAnswerSchema>;
