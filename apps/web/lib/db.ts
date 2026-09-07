import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { createDb, createInterviewRepository } from '@interview/db';

// `process.env.DATABASE_URL` is already an absolute path by the time this runs — resolved once in
// next.config.ts, specifically so nothing here needs its own `import.meta.url` trick (which would
// hit the same Turbopack bundling problem the token route hit — see next.config.ts's comment).
//
// The directory is created up front, mirroring `packages/db/src/migrate.ts` — without it, a build
// or dev server started before the first `pnpm db:migrate` crashes at module evaluation (every
// route is touched during Next's page-data collection, even ones that don't render this data)
// with a raw "directory does not exist" error instead of the clearer "no such table" a query
// against an empty, unmigrated file would give.
//
// This app is read-only by design (plan Risks: "Two processes both open the same SQLite file" —
// the agent worker is the only writer, WAL mode lets both share the file). Nothing in `apps/web`
// should import `createDb`/`createInterviewRepository` directly other than this module.
mkdirSync(dirname(process.env.DATABASE_URL!), { recursive: true });
const db = createDb(process.env.DATABASE_URL!);
export const interviewRepository = createInterviewRepository(db);
