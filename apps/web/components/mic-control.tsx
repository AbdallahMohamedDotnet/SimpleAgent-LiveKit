'use client';

import {
  useTrackToggle,
  useLocalParticipant,
  useMultibandTrackVolume,
} from '@livekit/components-react';
import { LocalAudioTrack, Track } from 'livekit-client';

/**
 * Microphone toggle that shows the live input level.
 *
 * A plain on/off button leaves "is it hearing me?" unanswerable, and a participant who thinks the
 * agent is slow is often actually unheard — so the button fills in proportion to measured input
 * volume, making a dead or muted mic obvious at a glance instead of after a failed turn.
 */
export function MicControl() {
  const { toggle, enabled, pending } = useTrackToggle({ source: Track.Source.Microphone });
  const { microphoneTrack } = useLocalParticipant();

  const track =
    microphoneTrack?.track instanceof LocalAudioTrack ? microphoneTrack.track : undefined;
  // One band is all this needs: overall loudness, not a spectrum.
  const [volume = 0] = useMultibandTrackVolume(track, { bands: 1 });
  // Speech sits low in the 0–1 range, so it is scaled up to make normal talking visible.
  const level = enabled ? Math.min(100, Math.round(volume * 260)) : 0;

  return (
    <button
      type="button"
      className="mic-toggle"
      data-enabled={enabled}
      disabled={pending}
      aria-pressed={enabled}
      onClick={() => void toggle()}
    >
      <span className="level" style={{ width: `${level}%` }} aria-hidden />
      <span className="icon" aria-hidden>
        {enabled ? '🎙️' : '🔇'}
      </span>
      <span className="label">{enabled ? 'Mic on' : 'Mic off'}</span>
    </button>
  );
}
