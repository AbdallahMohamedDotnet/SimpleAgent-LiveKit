# Recovery and retention operations

`interview cleanup` performs a startup catch-up pass: it prepares deletion jobs for interviews
whose start timestamp is at least 30 UTC days old, deletes only files recorded under the configured
owned recordings root, then removes the interview and all dependent SQLite rows. File failures
remain visible and retryable. A deletion job immediately hides its interview from reads and blocks
score-task claims or late result writes.

Run cleanup before starting the voice job or scoring worker, and schedule the same
command locally at least daily:

```bash
SQLITE_PATH=data/interviews.sqlite3 \
RECORDINGS_DIR=data/recordings \
UV_CACHE_DIR=.tools/uv-cache \
.tools/bin/uv run interview cleanup
```

For a user-level systemd timer, create `~/.config/systemd/user/interview-cleanup.service` with the
absolute project paths for this checkout:

```ini
[Unit]
Description=Delete expired local interview data

[Service]
Type=oneshot
WorkingDirectory=/absolute/path/to/LiveKit_CLI
Environment=SQLITE_PATH=/absolute/path/to/LiveKit_CLI/data/interviews.sqlite3
Environment=RECORDINGS_DIR=/absolute/path/to/LiveKit_CLI/data/recordings
Environment=UV_CACHE_DIR=/absolute/path/to/LiveKit_CLI/.tools/uv-cache
ExecStart=/absolute/path/to/LiveKit_CLI/.tools/bin/uv run interview cleanup
```

Create `~/.config/systemd/user/interview-cleanup.timer`:

```ini
[Unit]
Description=Run local interview retention cleanup daily

[Timer]
OnBootSec=5min
OnUnitActiveSec=1d
Persistent=true

[Install]
WantedBy=timers.target
```

After replacing every placeholder with an absolute owned path, validate and enable it:

```bash
systemd-analyze --user verify ~/.config/systemd/user/interview-cleanup.service
systemd-analyze --user verify ~/.config/systemd/user/interview-cleanup.timer
systemctl --user daemon-reload
systemctl --user enable --now interview-cleanup.timer
systemctl --user list-timers interview-cleanup.timer
```

The timer cannot delete data while the machine is off. `Persistent=true` requests a catch-up run
when the user manager returns, and application startup must still run the cleanup command. Local
deletion does not control provider retention or guarantee forensic erasure from storage media.

Recovery checkpoints preserve the stage, remaining active time, committed evidence identifiers,
room/candidate binding, and active recording segment. Reconnects have one fixed 120-second deadline.
A new room SID is recorded as a new connection attempt; it is never represented as the old live
room. Only an explicitly recorded interrupted question may be re-asked after resume.
