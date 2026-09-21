"""Read-only terminal status command for a dispatched interview."""

from __future__ import annotations

from interview_app.adapters.terminal import results_json, results_text
from interview_app.bootstrap import build_get_mission
from interview_app.domain.models import InterviewId
from interview_app.settings import LaunchSettings


async def run_status(
    settings: LaunchSettings,
    interview_id: InterviewId,
    *,
    as_json: bool,
) -> str:
    database, get_mission = build_get_mission(settings)
    await database.migrate()
    mission = await get_mission.execute(interview_id)
    if as_json:
        return results_json.render_mission(mission)
    return results_text.render_mission(mission)
