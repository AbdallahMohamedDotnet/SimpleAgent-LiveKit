import { AgentSession, defineAgent, type JobContext, type JobProcess } from '@livekit/agents';
import { InterviewSessionState } from '@interview/core';
import { createDb, createInterviewRepository, type InterviewRepository } from '@interview/db';
import { createModels, createTurnDetection, type Models } from './models.js';
import { config } from './config.js';
import { InterviewOrchestrator } from './interview/orchestrator.js';
import { OpenRouterProbePlanner } from './interview/probe-planner.js';
import { wireStatePersistence, wireTranscriptPersistence } from './interview/persistence.js';
import { wireProgressPublisher } from './interview/progress-publisher.js';
import type { InterviewUserData } from './interview/tools.js';

/** Per-process state built once in `prewarm`, before any participant is waiting on it. */
interface WarmState {
  models: Models;
  repo: InterviewRepository;
  planner: OpenRouterProbePlanner;
}

let warm: WarmState | undefined;

/**
 * Holds the current job's interview bookkeeping so `onSessionEnd` (below) can decide
 * completed-vs-abandoned. `JobContext` itself carries no per-job custom data field — only
 * `JobProcess.userData`, which is process-wide, pre-warm state, not per-job (dist/job.d.ts:145) —
 * so this is a module-scoped closure instead. Safe because a job process runs one job's
 * entry/onSessionEnd pair at a time, never two jobs concurrently.
 */
let activeInterview:
  { repo: InterviewRepository; interviewId: string; state: InterviewSessionState } | undefined;

/**
 * Builds everything that does not depend on the room, while the job process is still idle.
 *
 * This is pure latency work. Constructing the models opens the ElevenLabs websockets and the
 * OpenRouter connection pool, and `llm.prewarm()` completes the TLS handshake — all of which used
 * to happen inside `entry`, i.e. after a participant had already joined and was listening to
 * silence. Opening the SQLite file here rather than per job moves that off the path too.
 */
function prewarm(_proc: JobProcess): void {
  const models = createModels();
  models.llm.prewarm();
  warm = {
    models,
    repo: createInterviewRepository(createDb(config.DATABASE_URL)),
    planner: new OpenRouterProbePlanner({
      apiKey: config.OPENROUTER_API_KEY,
      model: config.PROBE_PLANNER_MODEL,
      timeoutMs: config.PROBE_PLANNER_TIMEOUT_MS,
    }),
  };
}

/** Falls back to building on demand if a job somehow starts without `prewarm` having run. */
function warmState(): WarmState {
  if (!warm) prewarm({} as JobProcess);
  return warm!;
}

async function entry(ctx: JobContext): Promise<void> {
  const { models, repo, planner } = warmState();

  // Strictly after `connect()`: `ctx.room.name` is only populated once the room is joined, so
  // starting the insert earlier to overlap the two records every interview under an empty room
  // name. The insert is a synchronous SQLite write anyway — there was nothing to overlap.
  await ctx.connect();
  const interviewId = await repo.createInterview({ roomName: ctx.room.name ?? '' });

  const state = new InterviewSessionState();
  activeInterview = { repo, interviewId, state };
  wireStatePersistence(state, repo, interviewId);
  wireProgressPublisher(ctx.room, state, interviewId);

  const session = new AgentSession<InterviewUserData>({
    ...models,
    // `vad` is intentionally not passed — see the note in models.js on why the auto-provisioned
    // Silero VAD's stock silence window is the one to want.
    userData: { state },
    turnHandling: {
      // Built here rather than in `prewarm`: the local detector binds to the job's inference
      // executor at construction time (see createTurnDetection).
      turnDetection: createTurnDetection(),
      endpointing: {
        minDelay: config.ENDPOINTING_MIN_DELAY_MS,
        maxDelay: config.ENDPOINTING_MAX_DELAY_MS,
      },
      preemptiveGeneration: {
        enabled: true,
        // Synthesise the reply before the turn is confirmed, so the first audio frame is already
        // buffered the moment the participant actually stops talking.
        preemptiveTts: config.PREEMPTIVE_TTS,
      },
    },
  });
  wireTranscriptPersistence(session, repo, interviewId);

  await session.start({ agent: new InterviewOrchestrator(planner), room: ctx.room });
}

export default defineAgent({
  prewarm,
  entry,
  onSessionEnd: async () => {
    const interview = activeInterview;
    activeInterview = undefined;
    if (!interview) return;
    // A natural finish already called `completeInterview` from wireStatePersistence when
    // `state.status` became 'completed'; anything else (dropped call, error) is abandoned.
    if (interview.state.status !== 'completed') {
      await interview.repo.abandonInterview(interview.interviewId);
    }
  },
});
