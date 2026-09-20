"""Retention cleanup process entrypoint support."""

from interview_app.adapters.artifacts import LocalArtifactStore
from interview_app.adapters.clock import SystemClock
from interview_app.adapters.sqlite import SqliteDatabase, SqliteRetentionStore
from interview_app.application.retention import CleanupExpiredInterviews, CleanupReport
from interview_app.settings import CleanupSettings


async def run_cleanup(settings: CleanupSettings) -> CleanupReport:
    database = SqliteDatabase(settings.sqlite_path)
    await database.migrate()
    cleanup = CleanupExpiredInterviews(
        store=SqliteRetentionStore(database),
        artifacts=LocalArtifactStore(settings.data_root),
        clock=SystemClock(),
    )
    return await cleanup.execute()
