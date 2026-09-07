import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import dotenv from 'dotenv';
import type { NextConfig } from 'next';

// Loaded here, not in a route handler: `next.config.ts` is read directly by the Next CLI in
// plain Node before the server starts, so a `dotenv.config()` here populates `process.env` for
// the whole process (route handlers included). A route handler is bundled by Turbopack, which
// statically resolves `new URL(..., import.meta.url)` and fails to build on a relative path that
// walks outside the app directory — verified: it does, with "Module not found" on exactly that
// line — so the repo-root `.env` must be loaded from here instead.
const repoRoot = fileURLToPath(new URL('../../', import.meta.url));
dotenv.config({ path: resolve(repoRoot, '.env') });

// Resolved to an absolute path here too, and written back into `process.env` — so that
// server-side code needing the SQLite file (the results API/page in Step 10) only ever reads
// `process.env.DATABASE_URL` and never has to do its own `import.meta.url` resolution, which
// would hit the same Turbopack bundling problem inside a route handler or page.
process.env.DATABASE_URL = resolve(repoRoot, process.env.DATABASE_URL ?? './data/interviews.db');

const nextConfig: NextConfig = {};

export default nextConfig;
