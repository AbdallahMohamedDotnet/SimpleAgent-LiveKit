import { inference } from '@livekit/agents';
import { STT as ElevenLabsSTT, TTS as ElevenLabsTTS } from '@livekit/agents-plugin-elevenlabs';
import { LLM as OpenAICompatLLM } from '@livekit/agents-plugin-openai';
import { config } from './config.js';

export interface Models {
  stt: ElevenLabsSTT;
  tts: ElevenLabsTTS;
  llm: OpenAICompatLLM;
}

/**
 * One factory for every provider-backed model the session uses. Keeping this in one function is
 * the whole extension point for swapping a vendor (plan Design > Extension points,
 * "createModels() provider factory") — e.g. dropping ElevenLabs STT for
 * `@livekit/agents-plugin-deepgram`, which is published at the same 1.8.0 line, touches only this
 * file.
 *
 * Every option set here is either required or a latency choice; the comments say which, because
 * "why is this not the default?" is the question a reader will have.
 *
 * Called once per *process* from `prewarm` rather than once per job, so the ElevenLabs websockets
 * and the OpenRouter connection pool are already warm when a participant joins (see
 * interviewer.ts). Only provider clients that reach the network over plain HTTP/websockets belong
 * here — the local inference models (VAD, turn detector) must be built per job instead; see
 * `createVad` below.
 */
export function createModels(): Models {
  const stt = new ElevenLabsSTT({
    apiKey: config.ELEVENLABS_API_KEY,
    model: 'scribe_v2_realtime',
    useRealtime: true,
    languageCode: 'en',
    // The interview vocabulary the model is most likely to mangle. Biasing STT towards it cuts
    // the re-ask loop ("sorry, could you repeat that?"), which is the most expensive kind of
    // latency there is — a whole extra turn.
    keyterms: ['LiveKit', 'TypeScript', 'Kubernetes', 'PostgreSQL', 'Figma', 'DevOps'],
  });

  const tts = new ElevenLabsTTS({
    apiKey: config.ELEVENLABS_API_KEY,
    voiceId: config.ELEVEN_VOICE_ID,
    model: 'eleven_flash_v2_5',
    // ElevenLabs' text normalisation ("1995" -> "nineteen ninety five") runs before synthesis and
    // measurably delays the first audio chunk. The flash models handle plain conversational text
    // fine without it, and this agent never reads out numbers or dates it generated itself.
    applyTextNormalization: 'off',
    // Highest latency optimisation the API offers. It trades a little prosody quality for a
    // shorter time-to-first-byte, which is the right trade in a back-and-forth interview.
    streamingLatency: 3,
    // Lets ElevenLabs decide chunk boundaries itself instead of buffering to our schedule, so
    // the first sentence starts playing as soon as it is synthesised.
    autoMode: true,
    voiceSettings: {
      stability: 0.5,
      similarity_boost: 0.75,
      // Slightly quicker than neutral delivery — the agent reads questions, not prose.
      speed: 1.05,
      use_speaker_boost: false,
    },
  });

  // OpenRouter exposes an OpenAI-compatible chat completions endpoint; the OpenAI plugin has no
  // dedicated `withOpenRouter` helper (verified: `grep -ri openrouter` over its dist/ turns up
  // nothing), so OpenRouter is configured through the generic baseURL/apiKey options.
  const llm = new OpenAICompatLLM({
    baseURL: 'https://openrouter.ai/api/v1',
    apiKey: config.OPENROUTER_API_KEY,
    model: config.OPENROUTER_MODEL,
    temperature: config.LLM_TEMPERATURE,
    // A hard ceiling on reply length. Without it a chatty model can produce a 30-second answer
    // that the participant experiences as the agent being slow to hand the turn back.
    maxCompletionTokens: config.LLM_MAX_TOKENS,
    // Each topic task exposes exactly one tool and the flow is strictly sequential, so parallel
    // calls can only produce out-of-order `record_*` calls the state machine would reject.
    parallelToolCalls: false,
  });

  return { stt, tts, llm };
}

/**
 * Deliberately absent: a VAD factory.
 *
 * `AgentSession` auto-provisions `inference.VAD({ model: 'silero' })` when `vad` is omitted, and
 * its stock options are the ones to want. The default `minSilenceDuration` of 250 ms is not a
 * round number — the SDK picks it so the silence window always satisfies the audio end-of-turn
 * detector's minimum (agents/dist/inference/vad.js:7-15). Lowering it to chase responsiveness
 * starves the detector: the agent joins the room, subscribes to the microphone, and then never
 * speaks at all, with no error logged. Verified against a live room.
 *
 * Responsiveness is tuned on the session's `endpointing.minDelay` instead, which is what actually
 * governs when the agent takes the turn.
 */

/**
 * Builds the configured end-of-turn detector, or returns the string mode when `TURN_DETECTOR` asks
 * for plain VAD/STT endpointing instead of a semantic model.
 *
 * Job-scoped for the same reason as `createVad`: `inference.TurnDetector`'s constructor resolves
 * the local model's executor from `getJobContext()` (agents/dist/inference/eot/detector.js:75), so
 * building it in `prewarm` would silently degrade it to a constant positive prediction.
 */
export function createTurnDetection() {
  if (config.TURN_DETECTOR === 'vad' || config.TURN_DETECTOR === 'stt') {
    return config.TURN_DETECTOR;
  }
  return new inference.TurnDetector({ version: config.TURN_DETECTOR });
}
