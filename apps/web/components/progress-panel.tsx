'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRoomContext } from '@livekit/components-react';
import type { TextStreamReader } from 'livekit-client';
import type { InterviewProgressMessage, InterviewTopic } from '@interview/core';

const PROGRESS_TOPIC = 'interview.progress';

const TOPIC_LABELS: Record<InterviewTopic, string> = {
  identity: 'Name & age',
  role: 'Your role',
  deepDive: 'Deep dive',
};
const TOPIC_ORDER: InterviewTopic[] = ['identity', 'role', 'deepDive'];

type StepStatus = 'done' | 'active' | 'pending';

/**
 * Live interview progress, driven by the snapshots the agent publishes on `interview.progress`.
 *
 * Beyond the three-step stepper, each completed step shows what was actually captured (the name
 * it heard, the job title, the deep-dive question count). That read-back is the participant's only
 * chance to notice a mis-heard answer while the interview is still running — the results page is
 * too late.
 */
export function ProgressPanel() {
  const room = useRoomContext();
  const [snapshot, setSnapshot] = useState<InterviewProgressMessage | null>(null);

  useEffect(() => {
    const handler = (reader: TextStreamReader) => {
      reader
        .readAll()
        .then((text) => setSnapshot(JSON.parse(text) as InterviewProgressMessage))
        .catch(() => {
          // A malformed snapshot just leaves the panel on its last good state.
        });
    };
    room.registerTextStreamHandler(PROGRESS_TOPIC, handler);
    return () => room.unregisterTextStreamHandler(PROGRESS_TOPIC);
  }, [room]);

  const doneCount = snapshot ? TOPIC_ORDER.filter((t) => isTopicDone(snapshot, t)).length : 0;

  return (
    <div className="panel room-progress">
      <h2 className="panel-title">
        <span>Progress</span>
        <span>{doneCount}/3</span>
      </h2>

      <div className="progress-bar" aria-hidden>
        <span style={{ width: `${(doneCount / TOPIC_ORDER.length) * 100}%` }} />
      </div>

      <ol className="steps" style={{ marginTop: '0.9rem' }}>
        {TOPIC_ORDER.map((topic, index) => {
          const status = stepStatus(snapshot, topic);
          return (
            <li key={topic} className="step" data-status={status}>
              <span className="step-marker" aria-hidden>
                {status === 'done' ? '✓' : index + 1}
              </span>
              <div>
                <div className="step-label">{TOPIC_LABELS[topic]}</div>
                <StepDetail snapshot={snapshot} topic={topic} status={status} />
              </div>
            </li>
          );
        })}
      </ol>

      {snapshot?.status === 'completed' && (
        <div className="completion-banner">
          <strong>Interview complete</strong>
          <Link href={`/interviews/${snapshot.interviewId}`}>View your results →</Link>
        </div>
      )}
    </div>
  );
}

/** What the agent captured for a step, or what it is doing on the step in progress. */
function StepDetail({
  snapshot,
  topic,
  status,
}: {
  snapshot: InterviewProgressMessage | null;
  topic: InterviewTopic;
  status: StepStatus;
}) {
  if (!snapshot) {
    // Only under the step that is about to start — repeating it under all three reads as three
    // separate things being waited on.
    return status === 'active' ? (
      <p className="step-detail">Waiting for the interview to begin…</p>
    ) : null;
  }

  if (topic === 'identity' && snapshot.identity) {
    return (
      <p className="step-detail">
        {snapshot.identity.fullName}, {snapshot.identity.age}
      </p>
    );
  }

  if (topic === 'role' && snapshot.role) {
    return (
      <>
        <p className="step-detail">
          {snapshot.role.jobTitle} · {snapshot.role.domain}
        </p>
        {snapshot.role.technologies.length > 0 && (
          <div className="chips">
            {snapshot.role.technologies.map((tech) => (
              <span className="chip" key={tech}>
                {tech}
              </span>
            ))}
          </div>
        )}
      </>
    );
  }

  if (topic === 'deepDive') {
    if (snapshot.deepDive) {
      return (
        <p className="step-detail">
          {snapshot.deepDive.turns.length} question
          {snapshot.deepDive.turns.length === 1 ? '' : 's'} answered
        </p>
      );
    }
    // The plan arrives before the first question is asked, so this is also the window in which
    // the agent is generating it — worth saying out loud so the pause reads as work, not a hang.
    if (status === 'active') {
      return (
        <p className="step-detail">
          {snapshot.probePlan
            ? `${snapshot.probePlan.questions.length} questions on ${snapshot.probePlan.topic}`
            : 'Preparing follow-up questions…'}
        </p>
      );
    }
  }

  if (status === 'active') {
    return <p className="step-detail">In progress…</p>;
  }
  return null;
}

function stepStatus(snapshot: InterviewProgressMessage | null, topic: InterviewTopic): StepStatus {
  if (!snapshot) return topic === 'identity' ? 'active' : 'pending';
  if (isTopicDone(snapshot, topic)) return 'done';
  if (snapshot.currentTopic === topic) return 'active';
  return 'pending';
}

function isTopicDone(snapshot: InterviewProgressMessage, topic: InterviewTopic): boolean {
  if (topic === 'identity') return snapshot.identity !== null;
  if (topic === 'role') return snapshot.role !== null;
  return snapshot.deepDive !== null;
}
