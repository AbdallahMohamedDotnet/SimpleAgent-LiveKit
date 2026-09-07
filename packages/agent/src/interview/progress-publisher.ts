import type { Room } from '@livekit/rtc-node';
import type { InterviewProgressMessage, InterviewSessionState } from '@interview/core';

/** Topic under which the interview snapshot is streamed to the room (plan Design > Patterns,
 * "Showing progress in the browser"). Shared verbatim with the browser's stream handler. */
export const PROGRESS_TOPIC = 'interview.progress';

/**
 * Pushes a JSON snapshot of `InterviewSessionState` to the room on every change, so the browser's
 * progress panel advances topic-by-topic live rather than only after the call ends. Returns an
 * unsubscribe function.
 *
 * `interviewId` rides along on every message because the browser has no other way to learn it —
 * it picks the room name, the agent picks the id — and the results page is addressed by id. Sent
 * on each message rather than once, since the browser may subscribe after the first snapshot.
 */
export function wireProgressPublisher(
  room: Room,
  state: InterviewSessionState,
  interviewId: string,
): () => void {
  return state.onChange((snapshot) => {
    const participant = room.localParticipant;
    if (!participant) return;
    const message: InterviewProgressMessage = { interviewId, ...snapshot };
    void participant.sendText(JSON.stringify(message), { topic: PROGRESS_TOPIC });
  });
}
