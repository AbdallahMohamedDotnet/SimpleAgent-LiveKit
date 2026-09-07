import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import dotenv from 'dotenv';

/**
 * The workspace root — three levels above this file (packages/db/src/env.ts -> packages/db/ ->
 * packages/ -> root). Anchoring on this rather than `process.cwd()` matters because `pnpm
 * --filter <pkg> <script>` runs scripts with cwd set to that package's own directory, not the
 * repo root, so a bare `dotenv/config` or a relative `DATABASE_URL` would silently resolve
 * per-package instead of against the one root `.env` and the one shared `data/` directory.
 */
const repoRoot = fileURLToPath(new URL('../../../', import.meta.url));

dotenv.config({ path: resolve(repoRoot, '.env') });

/** Resolves `DATABASE_URL` (default `./data/interviews.db`) against the repo root. */
export function resolveDatabaseUrl(): string {
  const raw = process.env.DATABASE_URL ?? './data/interviews.db';
  return resolve(repoRoot, raw);
}
