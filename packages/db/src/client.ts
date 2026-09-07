import Database from 'better-sqlite3';
import { drizzle, type BetterSQLite3Database } from 'drizzle-orm/better-sqlite3';
import * as schema from './schema.js';

export type Db = BetterSQLite3Database<typeof schema>;

/**
 * Opens the SQLite file and returns a drizzle handle over it. WAL mode lets the agent worker (the
 * only writer) and the Next.js app (read-only, by design — plan Risks: "Two processes both open
 * the same SQLite file") share the file concurrently.
 */
export function createDb(databaseUrl: string): Db {
  const sqlite = new Database(databaseUrl);
  sqlite.pragma('journal_mode = WAL');
  sqlite.pragma('foreign_keys = ON');
  return drizzle(sqlite, { schema });
}
