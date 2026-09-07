import { AgentTask } from '@livekit/agents';
import { identityAnswerSchema, identityInstructions, type IdentityAnswer } from '@interview/core';
import { createCompletionTool } from './tools.js';

/**
 * Topic 1 — name and age. Runs as a self-contained sub-conversation (plan Design > Approach):
 * the orchestrator awaits `new IdentityTask().run()` and gets back a typed `IdentityAnswer` once
 * `record_identity` fires.
 */
export class IdentityTask extends AgentTask<IdentityAnswer> {
  constructor() {
    super({
      instructions: identityInstructions(),
      tools: {
        record_identity: createCompletionTool({
          description:
            "Records the participant's full name and age once both have been clearly stated.",
          parameters: identityAnswerSchema,
          successMessage: 'Identity recorded.',
        }),
      },
    });
  }
}
