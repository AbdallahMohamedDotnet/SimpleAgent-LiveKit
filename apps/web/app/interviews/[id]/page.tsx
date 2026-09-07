import Link from 'next/link';
import { notFound } from 'next/navigation';
import { interviewRepository } from '@/lib/db';

export default async function InterviewResultsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const interview = await interviewRepository.getInterview(id);
  if (!interview) notFound();

  const duration = interview.completedAt
    ? Math.max(1, Math.round((interview.completedAt - interview.startedAt) / 60000))
    : null;

  return (
    <main style={{ justifyContent: 'flex-start', paddingTop: 'clamp(1.5rem, 6vh, 4rem)' }}>
      <div className="results">
        <header className="results-header">
          <div>
            <span className="eyebrow">Interview results</span>
            <h1>{interview.fullName ?? 'Unnamed participant'}</h1>
          </div>
          <span className="badge" data-status={interview.status}>
            {interview.status.replace('_', ' ')}
          </span>
        </header>

        <section className="panel">
          <h2 className="panel-title">
            <span>At a glance</span>
            {duration !== null && <span>{duration} min</span>}
          </h2>
          <dl className="facts">
            <div>
              <dt>Age</dt>
              <dd>{interview.age ?? '—'}</dd>
            </div>
            <div>
              <dt>Job title</dt>
              <dd>{interview.jobTitle ?? '—'}</dd>
            </div>
            <div>
              <dt>Domain</dt>
              <dd>{interview.domain ?? '—'}</dd>
            </div>
            <div>
              <dt>Seniority</dt>
              <dd>{interview.seniority ?? '—'}</dd>
            </div>
          </dl>

          {interview.technologies && interview.technologies.length > 0 && (
            <div className="chips" style={{ marginTop: '1rem' }}>
              {interview.technologies.map((tech) => (
                <span className="chip" key={tech}>
                  {tech}
                </span>
              ))}
            </div>
          )}
        </section>

        {interview.jobDescription && (
          <section className="panel">
            <h2 className="panel-title">
              <span>What they do</span>
            </h2>
            <p style={{ margin: 0 }}>{interview.jobDescription}</p>
          </section>
        )}

        <section className="panel">
          <h2 className="panel-title">
            <span>Deep dive</span>
            {interview.deepDiveTurns.length > 0 && <span>{interview.deepDiveTurns.length}</span>}
          </h2>

          {interview.deepDiveTurns.length === 0 ? (
            <p className="empty-note">
              {interview.status === 'in_progress'
                ? 'Still in progress — this fills in as the interview runs.'
                : 'No deep-dive answers were recorded.'}
            </p>
          ) : (
            <ol className="qa">
              {interview.deepDiveTurns.map((turn) => (
                <li key={turn.seq}>
                  <div>
                    <p className="question">{turn.question}</p>
                    <p className="answer">{turn.answer}</p>
                  </div>
                </li>
              ))}
            </ol>
          )}

          {interview.deepDiveSummary && (
            <p className="summary" style={{ marginTop: '1.25rem' }}>
              {interview.deepDiveSummary}
            </p>
          )}
        </section>

        <footer
          style={{
            display: 'flex',
            gap: '1rem',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
          }}
        >
          <Link href="/">← Start another interview</Link>
          <Link href={`/api/interviews/${interview.id}`}>View raw JSON</Link>
        </footer>
      </div>
    </main>
  );
}
