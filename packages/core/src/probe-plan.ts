import { probePlanSchema, type ProbePlan, type RoleAnswer } from './schemas.js';

/**
 * Turns a role answer into an ordered list of deep-dive questions. Kept as an interface so the
 * LLM-backed implementation (packages/agent) and this deterministic fallback are interchangeable
 * — the Dependency Inversion point the plan's SOLID review calls out, and what makes
 * `DeepDiveTask` testable with no network call.
 */
export interface ProbePlanner {
  plan(role: RoleAnswer): Promise<ProbePlan>;
}

/**
 * No-network fallback used when the LLM-backed planner fails validation twice in a row (plan
 * Design > Patterns, "Deciding topic 3 depends on topic 2"). Deliberately generic — it reasons
 * only from `role.jobTitle` / `role.domain` / `role.technologies`, never from a hardcoded list of
 * professions, which is what proves topic 3 stays adaptive even in the degraded path.
 */
export class StaticProbePlanner implements ProbePlanner {
  async plan(role: RoleAnswer): Promise<ProbePlan> {
    const techs = role.technologies;
    const techPhrase = techs.length > 0 ? ` using ${techs.join(', ')}` : '';
    const questions = [
      `Walk me through a recent project where you worked as a ${role.jobTitle}${techPhrase}.`,
      techs.length > 0
        ? `What's a specific challenge you've run into with ${techs[0]}, and how did you resolve it?`
        : `What's a specific challenge you've run into in ${role.domain}, and how did you resolve it?`,
      'What does a typical day look like for you in this role?',
    ];
    return probePlanSchema.parse({ topic: role.domain, questions });
  }
}
