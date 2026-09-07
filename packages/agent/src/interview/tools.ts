import { tool, type AgentTask, type AnonFunctionTool } from '@livekit/agents';
import type { InterviewSessionState } from '@interview/core';
import type { z } from 'zod';

/** Shared session state every interview task and tool reaches through `AgentSession.userData`
 * (plan Design > Patterns, "Sharing interview state across tasks and tools"). */
export interface InterviewUserData {
  state: InterviewSessionState;
}

/**
 * Builds the one function-tool each topic task uses to end its own sub-conversation. A tool's
 * `execute` runs long after the task's constructor returns, so it cannot close over `this`
 * directly — it reaches the currently-active task through `ctx.session.currentAgent`
 * (`AgentSession.currentAgent`, dist/voice/agent_session.d.ts:535), which is exactly this task at
 * the moment the model calls its own tool.
 *
 * Centralised here rather than duplicated per task (plan Design > Maintainability): three call
 * sites (identity, role, and the deep-dive's per-question tool in Step 6) would otherwise repeat
 * the exact same "parse args, complete the task, return an ack" shape.
 */
export function createCompletionTool<Schema extends z.ZodTypeAny, ResultT>(opts: {
  description: string;
  parameters: Schema;
  successMessage: string;
}): AnonFunctionTool<z.infer<Schema>, unknown, string> {
  return tool({
    description: opts.description,
    parameters: opts.parameters,
    execute: async (args, { ctx }) => {
      (ctx.session.currentAgent as AgentTask<ResultT>).complete(args as ResultT);
      return opts.successMessage;
    },
  });
}
