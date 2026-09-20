CREATE TABLE stage_scores (
    task_id TEXT PRIMARY KEY REFERENCES score_tasks(id) ON DELETE CASCADE,
    snapshot_id TEXT NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    stage_id TEXT NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
    rubric_version TEXT NOT NULL,
    model TEXT NOT NULL,
    average REAL,
    assessed_count INTEGER NOT NULL CHECK (assessed_count >= 0),
    total_count INTEGER NOT NULL CHECK (total_count >= assessed_count),
    summary TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(snapshot_id, rubric_version)
);

CREATE TABLE competency_scores (
    task_id TEXT NOT NULL REFERENCES stage_scores(task_id) ON DELETE CASCADE,
    competency TEXT NOT NULL,
    status TEXT NOT NULL,
    score INTEGER CHECK (score BETWEEN 1 AND 5),
    rationale TEXT NOT NULL,
    limitation TEXT,
    difficulty TEXT,
    assistance TEXT,
    PRIMARY KEY(task_id, competency)
);

CREATE TABLE score_evidence (
    task_id TEXT NOT NULL,
    competency TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE RESTRICT,
    quote TEXT NOT NULL,
    PRIMARY KEY(task_id, competency, ordinal),
    FOREIGN KEY(task_id, competency)
        REFERENCES competency_scores(task_id, competency) ON DELETE CASCADE
);
