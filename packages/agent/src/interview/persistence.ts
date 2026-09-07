import {
  AgentSessionEventTypes,
  ChatMessage,
  type AgentSession,
  type ConversationItemAddedEvent,
} from '@livekit/agents';
import type { InterviewSessionState, InterviewSnapshot } from '@interview/core';
import type { InterviewRepository } from '@interview/db';

/**
 * Write-through persistence (plan Design > Patterns, "Persisting without blocking the
 * conversation"): every `InterviewSessionState` mutation fires the matching repository write(s),
 * fire-and-forget, so a completed topic survives a crash even if the interview itself never
 * finishes. Returns an unsubscribe function.
 *
 * Deep-dive turns are written together, all at once, the moment topic 3 completes —
 * `DeepDiveTask` bundles every turn into one `AgentTask` result rather than exposing them one at
 * a time, so this cannot observe (and therefore cannot persist) a turn mid-deep-dive. A crash
 * between two deep-dive questions loses that partial progress; identity and role do not have this
 * gap, since each is its own topic and is written the moment its own task completes.
 */
export function wireStatePersistence(
  state: InterviewSessionState,
  repo: InterviewRepository,
  interviewId: string,
): () => void {
  const written = { identity: false, role: false, probePlan: false, deepDive: false };

  return state.onChange((snapshot: InterviewSnapshot) => {
    if (snapshot.identity && !written.identity) {
      written.identity = true;
      void repo.saveIdentity(interviewId, snapshot.identity);
    }
    if (snapshot.role && !written.role) {
      written.role = true;
      void repo.saveRole(interviewId, snapshot.role);
    }
    if (snapshot.probePlan && !written.probePlan) {
      written.probePlan = true;
      void repo.saveProbePlan(interviewId, snapshot.probePlan);
    }
    if (snapshot.deepDive && !written.deepDive) {
      written.deepDive = true;
      snapshot.deepDive.turns.forEach((turn, seq) => {
        void repo.appendProbeTurn(interviewId, seq, turn);
      });
    }
    if (snapshot.status === 'completed') {
      void repo.completeInterview(interviewId, snapshot.deepDive?.summary ?? '');
    }
  });
}

/**
 * Mirrors every chat message (both roles) added during the session into `transcript_turns`, for
 * the live transcript panel and the post-call results view. Returns an unsubscribe function.
 */
export function wireTranscriptPersistence(
  session: AgentSession<unknown>,
  repo: InterviewRepository,
  interviewId: string,
): () => void {
  let seq = 0;
  const handler = (ev: ConversationItemAddedEvent) => {
    if (!(ev.item instanceof ChatMessage)) return; // skip agent-handoff items — not a spoken turn
    const role = ev.item.role === 'assistant' ? 'agent' : ev.item.role === 'user' ? 'user' : null;
    const text = ev.item.textContent;
    if (!role || !text) return;
    void repo.appendTranscriptTurn(interviewId, seq++, { role, text });
  };
  session.on(AgentSessionEventTypes.ConversationItemAdded, handler);
  return () => session.off(AgentSessionEventTypes.ConversationItemAdded, handler);
}
