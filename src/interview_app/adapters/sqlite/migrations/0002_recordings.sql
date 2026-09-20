CREATE TABLE recordings (
    id TEXT PRIMARY KEY,
    interview_id TEXT NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
    sample_rate_hz INTEGER NOT NULL CHECK (sample_rate_hz > 0),
    channels INTEGER NOT NULL CHECK (channels > 0),
    sample_width_bytes INTEGER NOT NULL CHECK (sample_width_bytes > 0),
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    status TEXT NOT NULL,
    failure TEXT
);

CREATE TABLE recording_segments (
    id TEXT PRIMARY KEY,
    recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    stage_id TEXT NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
    speaker TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    offset_seconds REAL NOT NULL CHECK (offset_seconds >= 0),
    duration_seconds REAL NOT NULL CHECK (duration_seconds >= 0),
    checksum_sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    gaps_json TEXT NOT NULL,
    UNIQUE(recording_id, relative_path)
);

CREATE INDEX recording_segments_recording_idx
ON recording_segments(recording_id, offset_seconds, id);
