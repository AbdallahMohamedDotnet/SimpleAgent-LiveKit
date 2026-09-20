ALTER TABLE interviews ADD COLUMN room_name TEXT;
ALTER TABLE interviews ADD COLUMN room_sid TEXT;
ALTER TABLE interviews ADD COLUMN candidate_identity TEXT;
ALTER TABLE stages ADD COLUMN session_reference TEXT;

CREATE UNIQUE INDEX one_active_interview_idx
ON interviews((1))
WHERE state NOT IN ('interview_finished', 'incomplete');

CREATE TABLE events (
    id TEXT PRIMARY KEY,
    interview_id TEXT NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
    stage_id TEXT NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
    stage_kind TEXT NOT NULL,
    type TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE INDEX events_interview_time_idx ON events(interview_id, occurred_at, id);
