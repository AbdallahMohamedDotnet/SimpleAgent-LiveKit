CREATE TABLE interviews (
    id TEXT PRIMARY KEY,
    candidate_name TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE stages (
    id TEXT PRIMARY KEY,
    interview_id TEXT NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE turns (
    id TEXT PRIMARY KEY,
    stage_id TEXT NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
    speaker TEXT NOT NULL,
    text TEXT NOT NULL,
    is_final INTEGER NOT NULL CHECK (is_final IN (0, 1)),
    delivery_status TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE INDEX turns_stage_time_idx ON turns(stage_id, occurred_at, id);

CREATE TABLE snapshots (
    id TEXT PRIMARY KEY,
    stage_id TEXT NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
    rubric_version TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    content_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(stage_id, rubric_version)
);

CREATE TABLE score_tasks (
    id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    rubric_version TEXT NOT NULL,
    state TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    lease_owner TEXT,
    lease_expires_at TEXT,
    available_at TEXT NOT NULL,
    failure TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE(snapshot_id, rubric_version)
);

CREATE INDEX score_tasks_claim_idx
ON score_tasks(state, available_at, lease_expires_at, created_at);
