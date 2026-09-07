import { NextResponse } from 'next/server';
import { AccessToken, RoomAgentDispatch, RoomConfiguration } from 'livekit-server-sdk';

// The repo-root `.env` is loaded in next.config.ts, not here — see that file's comment for why a
// route handler (bundled by Turbopack) can't do this `import.meta.url` trick itself. By the time
// any request reaches this handler, `process.env` already has everything `.env` set.
const AGENT_NAME = process.env.LIVEKIT_AGENT_NAME ?? 'interviewer';

export async function POST(request: Request) {
  const { roomName, participantName } = (await request.json()) as {
    roomName?: string;
    participantName?: string;
  };

  if (!roomName || !participantName || participantName.trim().length === 0) {
    return NextResponse.json(
      { error: 'roomName and participantName are required' },
      { status: 400 },
    );
  }

  const livekitUrl = process.env.LIVEKIT_URL;
  const apiKey = process.env.LIVEKIT_API_KEY;
  const apiSecret = process.env.LIVEKIT_API_SECRET;

  if (!livekitUrl || !apiKey || !apiSecret) {
    return NextResponse.json(
      { error: 'Server is missing LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET' },
      { status: 500 },
    );
  }

  const identity = `participant-${crypto.randomUUID()}`;

  const token = new AccessToken(apiKey, apiSecret, { identity, name: participantName });
  token.addGrant({ room: roomName, roomJoin: true, canPublish: true, canSubscribe: true });
  // Explicit dispatch (plan Steps > 4/9): the agent worker registers with `agentName: 'interviewer'`
  // and only accepts jobs dispatched to that name — this is what asks the LiveKit server to send
  // this specific agent into the room the token is minted for.
  token.roomConfig = new RoomConfiguration({
    name: roomName,
    agents: [new RoomAgentDispatch({ agentName: AGENT_NAME })],
  });

  return NextResponse.json({
    token: await token.toJwt(),
    url: process.env.NEXT_PUBLIC_LIVEKIT_URL ?? livekitUrl,
  });
}
