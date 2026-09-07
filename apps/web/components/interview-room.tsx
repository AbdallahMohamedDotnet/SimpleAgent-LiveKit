'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { LiveKitRoom, RoomAudioRenderer, StartAudio } from '@livekit/components-react';
import { AgentStage } from './agent-stage';
import { MicControl } from './mic-control';
import { ProgressPanel } from './progress-panel';
import { TranscriptPanel } from './transcript-panel';

interface TokenResponse {
  token: string;
  url: string;
}

export function InterviewRoom({
  roomName,
  participantName,
}: {
  roomName: string;
  participantName: string;
}) {
  const router = useRouter();
  const [connection, setConnection] = useState<TokenResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Bumped by "Try again", which re-runs the token fetch without a full page reload.
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    fetch('/api/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roomName, participantName }),
    })
      .then(async (res) => {
        if (!res.ok) {
          const body = (await res.json().catch(() => ({}))) as { error?: string };
          throw new Error(body.error ?? `Token request failed (${res.status})`);
        }
        return res.json() as Promise<TokenResponse>;
      })
      .then((data) => {
        if (!cancelled) setConnection(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to connect');
      });
    return () => {
      cancelled = true;
    };
  }, [roomName, participantName, attempt]);

  const leave = useCallback(() => router.push('/'), [router]);

  if (error) {
    return (
      <main>
        <div className="card">
          <h1>Couldn&apos;t connect</h1>
          <p className="error-text">{error}</p>
          <button className="primary-action" onClick={() => setAttempt((n) => n + 1)}>
            Try again
          </button>
          <p style={{ marginTop: '1rem', textAlign: 'center' }}>
            <Link href="/">← Back to start</Link>
          </p>
        </div>
      </main>
    );
  }

  if (!connection) {
    return (
      <main>
        <div className="card">
          <span className="eyebrow">Please wait</span>
          <h1>Setting up your room…</h1>
          <p>Getting an access token and waking the interviewer.</p>
        </div>
      </main>
    );
  }

  return (
    <main>
      <LiveKitRoom
        serverUrl={connection.url}
        token={connection.token}
        connect
        audio
        onDisconnected={leave}
        onError={(err) => setError(err.message)}
      >
        <div className="room-shell">
          <div className="room-stage">
            <AgentStage />
            <div className="controls-row">
              <MicControl />
              <button className="ghost" onClick={leave}>
                End interview
              </button>
            </div>
            {/* Autoplay policies can block the agent's audio outright. Without this the room looks
                connected and the agent looks unresponsive, which is indistinguishable from
                latency. The button hides itself as soon as playback is allowed. */}
            <StartAudio label="🔊 Tap to enable sound" />
          </div>

          <ProgressPanel />
          <TranscriptPanel />
        </div>
        <RoomAudioRenderer />
      </LiveKitRoom>
    </main>
  );
}
