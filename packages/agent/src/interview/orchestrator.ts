import { Agent } from '@livekit/agents';
import type { ProbePlanner } from '@interview/core';
import { IdentityTask } from './identity-task.js';
import { RoleTask } from './role-task.js';
import { DeepDiveTask } from './deep-dive-task.js';
import type { InterviewUserData } from './tools.js';

const GREETING = "Hi! I'm your interview assistant. Let's start with your name and age.";
/**
 * Spoken *while* the probe plan is being generated. Topic 3's questions depend on topic 2's
 * answers, so the planner call cannot be started any earlier — but it does not have to be silent.
 * Kept to roughly the planner's own budget so the participant is never left waiting on nothing.
 */
const PLANNING_BRIDGE = 'Great — give me one second to line up a few follow-ups on that.';
const CLOSING = "That's everything I needed — thank you so much for your time!";

/**
 * Drives the three interview topics in a fixed order (plan Design > Approach). Sequencing lives
 * here as plain awaited TypeScript rather than in a prompt or in the model's discretion — see the
 * plan's Hard constraints: `AgentTask.run()` may only be awaited from a tool or from an Agent's
 * `onEnter`/`onExit`, which is exactly where this runs.
 *
 * `planner` is constructor-injected (plan Design > SOLID review, Dependency Inversion) so this
 * class can be driven by the real `OpenRouterProbePlanner` in production and by a stub planner in
 * tests, with no network involved in the latter.
 */
export class InterviewOrchestrator extends Agent<InterviewUserData> {
  #planner: ProbePlanner;

  constructor(planner: ProbePlanner) {
    super({
      instructions:
        'You orchestrate a structured interview. Sub-tasks handle the actual conversation with the participant; you do not ask questions directly.',
    });
    this.#planner = planner;
  }

  override async onEnter(): Promise<void> {
    const { state } = this.session.userData;

    this.session.say(GREETING);

    const identity = await new IdentityTask().run();
    state.record('identity', identity);

    const role = await new RoleTask(identity.fullName).run();
    state.record('role', role);

    // Deliberately not awaited before `plan()`: `say` returns a handle immediately, so the bridge
    // line is being synthesised and played over the same window the planner spends thinking,
    // instead of after it. This is the single longest non-conversational pause in the interview.
    this.session.say(PLANNING_BRIDGE);
    const plan = await this.#planner.plan(role);
    state.setProbePlan(plan);

    const deepDive = await new DeepDiveTask(plan).run();
    state.record('deepDive', deepDive);

    this.session.say(CLOSING);
    state.markComplete();
  }
}
