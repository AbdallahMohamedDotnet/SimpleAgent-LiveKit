'use client';

import { BarVisualizer, useVoiceAssistant, type AgentState } from '@livekit/components-react';

/**
 * The focal point of the room: an audio-reactive visualiser of the agent's own voice, plus the
 * one-word state label.
 *
 * The visualiser is doing real work rather than decoration — it is the fastest signal that the
 * agent is alive. During `thinking` there is no audio to react to, so the shared halo animation
 * (see `.stage[data-state='thinking']` in globals.css) carries the "still working" signal that a
 * silent gap otherwise reads as a hang.
 */
export function AgentStage() {
  const { state, audioTrack } = useVoiceAssistant();

  return (
    <div className="stage" data-state={state}>
      <div className="visualizer">
        <BarVisualizer
          state={state}
          track={audioTrack}
          barCount={7}
          // A visible floor: at rest the bars should still read as a row of bars, not dots.
          options={{ minHeight: 22, maxHeight: 90 }}
        />
      </div>
      <div className="status-pill" data-state={state} role="status" aria-live="polite">
        <span className="dot" aria-hidden />
        {describeState(state)}
      </div>
    </div>
  );
}

function describeState(state: AgentState): string {
  switch (state) {
    case 'listening':
      return 'Listening — go ahead';
    case 'thinking':
      return 'Thinking…';
    case 'speaking':
      return 'Speaking';
    case 'connecting':
    case 'initializing':
      return 'Connecting to the interviewer…';
    case 'failed':
      return 'The agent ran into a problem';
    case 'disconnected':
      return 'Waiting for the interviewer to join…';
    default:
      return 'Waiting for the interviewer…';
  }
}
