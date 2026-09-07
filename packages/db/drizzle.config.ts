import { defineConfig } from 'drizzle-kit';
import { resolveDatabaseUrl } from './src/env.js';

export default defineConfig({
  schema: './src/schema.ts',
  out: './drizzle',
  dialect: 'sqlite',
  dbCredentials: {
    url: resolveDatabaseUrl(),
  },
});
