'use client';

import { useEffect, useRef } from 'react';
import { useTranscriptions, useLocalParticipant } from '@livekit/components-react';

/**
 * Live transcript of the call.
 *
 * Auto-scrolls to the newest turn, but only when the reader is already at the bottom — scrolling
 * someone back down while they are reading an earlier answer is worse than letting the view fall
 * behind.
 */
export function TranscriptPanel() {
  const transcriptions = useTranscriptions();
  const { localParticipant } = useLocalParticipant();
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinnedToBottom = useRef(true);

  const turns = [...transcriptions]
    .sort((a, b) => a.streamInfo.timestamp - b.streamInfo.timestamp)
    .map((t) => ({
      role: t.participantInfo.identity === localParticipant.identity ? 'you' : 'agent',
      text: t.text,
      id: t.streamInfo.id,
    }));

  useEffect(() => {
    const el = scrollRef.current;
    if (el && pinnedToBottom.current) el.scrollTop = el.scrollHeight;
  }, [turns.length, turns.at(-1)?.text]);

  return (
    <div className="panel room-transcript">
      <h2 className="panel-title">
        <span>Transcript</span>
        {turns.length > 0 && <span>{turns.length}</span>}
      </h2>

      {turns.length === 0 ? (
        <p className="empty-note">Everything either of you says will appear here as you talk.</p>
      ) : (
        <div
          className="transcript-scroll"
          ref={scrollRef}
          onScroll={(e) => {
            const el = e.currentTarget;
            pinnedToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
          }}
        >
          {turns.map((turn) => (
            <div className="turn" data-role={turn.role} key={turn.id}>
              <span className="turn-role">{turn.role === 'you' ? 'You' : 'Interviewer'}</span>
              <p className="turn-text">{turn.text}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
