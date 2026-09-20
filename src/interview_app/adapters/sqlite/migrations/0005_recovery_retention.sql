ALTER TABLE interviews ADD COLUMN incomplete_reason TEXT;

CREATE TABLE recovery_checkpoints (
    interview_id TEXT PRIMARY KEY REFERENCES interviews(id) ON DELETE CASCADE,
    stage_id TEXT NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
    stage_kind TEXT NOT NULL,
    resumable_state TEXT NOT NULL,
    remaining_active_seconds REAL NOT NULL CHECK (remaining_active_seconds >= 0),
    last_committed_turn_id TEXT REFERENCES turns(id) ON DELETE SET NULL,
    last_committed_event_id TEXT REFERENCES events(id) ON DELETE SET NULL,
    interrupted_question_turn_id TEXT REFERENCES turns(id) ON DELETE SET NULL,
    room_name TEXT NOT NULL,
    room_sid TEXT NOT NULL,
    candidate_identity TEXT NOT NULL,
    active_recording_segment_id TEXT REFERENCES recording_segments(id) ON DELETE SET NULL,
    recovery_started_at TEXT,
    recovery_deadline_at TEXT,
    recovery_attempts INTEGER NOT NULL CHECK (recovery_attempts >= 0),
    updated_at TEXT NOT NULL
);

CREATE TABLE connection_attempts (
    id TEXT PRIMARY KEY,
    interview_id TEXT NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
    previous_room_sid TEXT NOT NULL,
    connected_room_sid TEXT,
    attempted_at TEXT NOT NULL,
    succeeded INTEGER NOT NULL CHECK (succeeded IN (0, 1)),
    failure TEXT
);

CREATE INDEX connection_attempts_interview_time_idx
ON connection_attempts(interview_id, attempted_at, id);

-- Deliberately has no foreign key: a content-free completion receipt survives row deletion.
CREATE TABLE deletion_jobs (
    interview_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    artifact_paths_json TEXT NOT NULL,
    failed_paths_json TEXT NOT NULL,
    attempts INTEGER NOT NULL CHECK (attempts >= 0),
    last_error TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX deletion_jobs_state_created_idx ON deletion_jobs(state, created_at);
