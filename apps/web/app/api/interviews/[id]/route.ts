import { NextResponse } from 'next/server';
import { interviewRepository } from '@/lib/db';

export async function GET(_request: Request, ctx: RouteContext<'/api/interviews/[id]'>) {
  const { id } = await ctx.params;
  const interview = await interviewRepository.getInterview(id);
  if (!interview) {
    return NextResponse.json({ error: 'Interview not found' }, { status: 404 });
  }
  return NextResponse.json(interview);
}
