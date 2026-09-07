import { fileURLToPath } from 'node:url';
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { migrate } from 'drizzle-orm/better-sqlite3/migrator';
import { resolveDatabaseUrl } from './env.js';
import { createDb } from './client.js';

const databaseUrl = resolveDatabaseUrl();
mkdirSync(dirname(databaseUrl), { recursive: true });

const migrationsFolder = fileURLToPath(new URL('../drizzle', import.meta.url));

const db = createDb(databaseUrl);
migrate(db, { migrationsFolder });

console.log(`Migrations applied to ${databaseUrl}`);
