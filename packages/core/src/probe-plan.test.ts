import { describe, expect, it } from 'vitest';
import { StaticProbePlanner } from './probe-plan.js';
import type { RoleAnswer } from './schemas.js';

const softwareEngineer: RoleAnswer = {
  jobTitle: 'Software Engineer',
  jobDescription: 'Builds backend services for a fintech product',
  domain: 'backend software engineering',
  technologies: ['C#', '.NET'],
};

const chef: RoleAnswer = {
  jobTitle: 'Chef',
  jobDescription: 'Runs the kitchen at a mid-size restaurant',
  domain: 'culinary arts',
  technologies: [],
};

describe('StaticProbePlanner', () => {
  it('produces questions naming the stated technologies for a technical role', async () => {
    const planner = new StaticProbePlanner();
    const plan = await planner.plan(softwareEngineer);
    expect(plan.topic).toBe('backend software engineering');
    const joined = plan.questions.join(' ');
    expect(joined).toContain('C#');
    expect(joined).toContain('.NET');
  });

  it('produces domain-grounded questions with no code-flavored language for a non-technical role', async () => {
    const planner = new StaticProbePlanner();
    const plan = await planner.plan(chef);
    expect(plan.topic).toBe('culinary arts');
    const joined = plan.questions.join(' ');
    expect(joined).toContain('culinary arts');
    expect(joined).not.toMatch(/C#|\.NET|code|software/i);
  });

  it('always returns a schema-valid plan with at least one question', async () => {
    const planner = new StaticProbePlanner();
    const plan = await planner.plan(chef);
    expect(plan.questions.length).toBeGreaterThan(0);
  });
});
