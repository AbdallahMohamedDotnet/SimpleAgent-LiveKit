import { AgentTask } from '@livekit/agents';
import { roleAnswerSchema, roleInstructions, type RoleAnswer } from '@interview/core';
import { createCompletionTool } from './tools.js';

/**
 * Topic 2 — job title, description, domain, and technologies. Takes the participant's name from
 * topic 1 so its instructions read as a continuous conversation rather than a fresh interview.
 */
export class RoleTask extends AgentTask<RoleAnswer> {
  constructor(fullName: string) {
    super({
      instructions: roleInstructions(fullName),
      tools: {
        record_role: createCompletionTool({
          description:
            'Records the job title, job description, domain, and technologies once known.',
          parameters: roleAnswerSchema,
          successMessage: 'Role recorded.',
        }),
      },
    });
  }
}
