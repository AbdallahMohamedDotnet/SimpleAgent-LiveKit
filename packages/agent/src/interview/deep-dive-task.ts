import { AgentTask, tool } from '@livekit/agents';
import {
  deepDiveTurnSchema,
  deepDiveInstructions,
  summarizeDeepDive,
  type DeepDiveAnswer,
  type DeepDiveTurn,
  type ProbePlan,
} from '@interview/core';

/**
 * Topic 3 — walks the adaptive `ProbePlan` question by question, recording one turn per model
 * call to `record_probe_answer`, and completes itself once every planned question has an answer
 * (plan Steps > 6: "DeepDiveTask receives the plan, walks it question by question, ... completing
 * when the list is exhausted"). Unlike `IdentityTask`/`RoleTask`, its tool accumulates state
 * across multiple calls, so it is not built from the shared `createCompletionTool` helper — but it
 * completes itself the same way they do, through `ctx.session.currentAgent` (see tools.ts).
 */
export class DeepDiveTask extends AgentTask<DeepDiveAnswer> {
  constructor(plan: ProbePlan) {
    const turns: DeepDiveTurn[] = [];
    super({
      instructions: deepDiveInstructions(plan.topic, plan.questions),
      tools: {
        record_probe_answer: tool({
          description: 'Records one question-and-answer pair from the deep dive.',
          parameters: deepDiveTurnSchema,
          execute: async (args, { ctx }) => {
            turns.push(args);
            if (turns.length >= plan.questions.length) {
              (ctx.session.currentAgent as DeepDiveTask).complete({
                turns: [...turns],
                summary: summarizeDeepDive(turns),
              });
              return 'All questions answered — thank you.';
            }
            return `Recorded. Next question: ${plan.questions[turns.length]}`;
          },
        }),
      },
    });
  }
}
