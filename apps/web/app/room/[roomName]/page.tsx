import { InterviewRoom } from '@/components/interview-room';

export default async function RoomPage({
  params,
  searchParams,
}: {
  params: Promise<{ roomName: string }>;
  searchParams: Promise<{ name?: string }>;
}) {
  const { roomName } = await params;
  const { name } = await searchParams;
  const participantName = name?.trim() || 'Guest';

  return <InterviewRoom roomName={roomName} participantName={participantName} />;
}
