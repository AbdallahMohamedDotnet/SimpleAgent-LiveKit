'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

/**
 * Requests microphone access before navigating.
 *
 * Doing it here rather than letting the room prompt on connect means the permission dialog is
 * answered while nothing is happening, instead of while the agent is already speaking its
 * greeting into a muted room. The returned track is stopped immediately — this is only for the
 * permission grant; the room publishes its own.
 */
async function primeMicrophone(): Promise<void> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  stream.getTracks().forEach((track) => track.stop());
}

export default function HomePage() {
  const router = useRouter();
  const [name, setName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function startInterview() {
    const trimmed = name.trim();
    if (!trimmed || submitting) return;
    setSubmitting(true);
    setError(null);

    try {
      await primeMicrophone();
    } catch {
      setSubmitting(false);
      setError('Microphone access is required — allow it in your browser, then try again.');
      return;
    }

    const roomName = `interview-${crypto.randomUUID()}`;
    router.push(`/room/${roomName}?name=${encodeURIComponent(trimmed)}`);
  }

  return (
    <main>
      <div className="card">
        <span className="eyebrow">Voice interview</span>
        <h1>Let&apos;s talk about your work</h1>
        <p>
          An AI interviewer will ask three short things — who you are, what you do, and then a few
          follow-ups built from your answers. It takes about five minutes, out loud.
        </p>

        <ol className="steps" style={{ marginBottom: '1.5rem' }}>
          {[
            ['Name & age', 'A quick introduction.'],
            ['Your role', 'What you actually do day to day.'],
            ['Deep dive', 'Questions written from what you just said.'],
          ].map(([label, detail], index) => (
            <li className="step" data-status="pending" key={label}>
              <span className="step-marker" aria-hidden>
                {index + 1}
              </span>
              <div>
                <div className="step-label">{label}</div>
                <p className="step-detail">{detail}</p>
              </div>
            </li>
          ))}
        </ol>

        <div className="field">
          <label htmlFor="participant-name">Your name</label>
          <input
            id="participant-name"
            type="text"
            placeholder="e.g. Alex Rivera"
            autoComplete="name"
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void startInterview();
            }}
          />
        </div>

        <button
          className="primary-action"
          onClick={() => void startInterview()}
          disabled={submitting || name.trim().length === 0}
        >
          {submitting ? 'Starting…' : 'Start interview →'}
        </button>

        {error && <p className="error-text">{error}</p>}

        <p className="empty-note" style={{ marginTop: '1rem', textAlign: 'center' }}>
          You&apos;ll be asked for microphone access.
        </p>
      </div>
    </main>
  );
}
