"""LiveKit room and explicit-dispatch adapter for the terminal launch commands."""

import json

from livekit import api

from interview_app.application.ports.interview_launch import (
    InterviewLaunchError,
    LaunchBinding,
    LaunchRequest,
    LaunchStatus,
)
from interview_app.settings import Secret


class LiveKitInterviewLaunchGateway:
    def __init__(
        self,
        *,
        url: str,
        api_key: Secret,
        api_secret: Secret,
        agent_name: str,
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._api_secret = api_secret
        self._agent_name = agent_name

    async def launch(self, request: LaunchRequest) -> LaunchBinding:
        client = self._client()
        room_created = False
        try:
            metadata = json.dumps(
                {
                    "interview_id": str(request.interview_id),
                    "candidate_identity": request.candidate_identity,
                },
                separators=(",", ":"),
            )
            room = await client.room.create_room(
                api.CreateRoomRequest(
                    name=request.room_name,
                    empty_timeout=600,
                    departure_timeout=120,
                    max_participants=4,
                    metadata=metadata,
                )
            )
            room_created = True
            dispatch = await client.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name=self._agent_name,
                    room=request.room_name,
                    metadata=metadata,
                )
            )
            return LaunchBinding(room_sid=room.sid, dispatch_id=dispatch.id)
        except Exception as error:
            if room_created:
                try:
                    await client.room.delete_room(api.DeleteRoomRequest(room=request.room_name))
                except Exception as cleanup_error:
                    failures = ExceptionGroup(
                        "LiveKit launch and room cleanup both failed.",
                        [error, cleanup_error],
                    )
                    raise InterviewLaunchError(
                        "LiveKit dispatch failed and the new room could not be cleaned up."
                    ) from failures
            raise InterviewLaunchError(
                "LiveKit could not create the interview room and agent dispatch."
            ) from error
        finally:
            await client.aclose()

    async def get_status(
        self,
        *,
        room_name: str,
        candidate_identity: str,
    ) -> LaunchStatus:
        client = self._client()
        try:
            rooms = await client.room.list_rooms(api.ListRoomsRequest(names=[room_name]))
            if not rooms.rooms:
                return LaunchStatus(False, False, False, False)
            dispatches = await client.agent_dispatch.list_dispatch(room_name)
            participants = await client.room.list_participants(
                api.ListParticipantsRequest(room=room_name)
            )
            matching_dispatches = [
                dispatch for dispatch in dispatches if dispatch.agent_name == self._agent_name
            ]
            return LaunchStatus(
                room_available=True,
                dispatch_created=bool(matching_dispatches),
                agent_joined=any(
                    job.state.status == api.JobStatus.JS_RUNNING
                    for dispatch in matching_dispatches
                    for job in dispatch.state.jobs
                ),
                candidate_joined=any(
                    participant.identity == candidate_identity
                    for participant in participants.participants
                ),
            )
        except Exception as error:
            raise InterviewLaunchError("LiveKit interview status is unavailable.") from error
        finally:
            await client.aclose()

    async def cancel(self, room_name: str) -> None:
        client = self._client()
        try:
            await client.room.delete_room(api.DeleteRoomRequest(room=room_name))
        except Exception as error:
            raise InterviewLaunchError("LiveKit could not cancel the interview room.") from error
        finally:
            await client.aclose()

    def _client(self) -> api.LiveKitAPI:
        return api.LiveKitAPI(
            url=self._url,
            api_key=self._api_key.reveal(),
            api_secret=self._api_secret.reveal(),
        )
