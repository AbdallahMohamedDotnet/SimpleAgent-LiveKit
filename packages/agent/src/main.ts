import { fileURLToPath } from 'node:url';
import { cli, ServerOptions } from '@livekit/agents';
import { config } from './config.js';

// Resolved explicitly rather than via `import.meta.filename` on this file (main.ts), because the
// worker dynamically imports whatever `agent` path is given and that must point at the module
// with the `defineAgent(...)` default export — interviewer.ts, not this entrypoint (see plan
// Steps > 3, and dist/worker.d.ts:68-71: "Path to a file that has Agent as a default export").
const agentPath = fileURLToPath(new URL('./interviewer.ts', import.meta.url));

// `agentName` is passed explicitly (rather than left to ServerOptions' own fallback to the raw
// `LIVEKIT_AGENT_NAME` env var — dist/worker.js:186) so the worker only accepts jobs dispatched
// to this name, and so the name goes through our own validated `config`, not a second read of
// `process.env` (dist/worker.d.ts:87-94: explicit dispatch).
cli.runApp(new ServerOptions({ agent: agentPath, agentName: config.LIVEKIT_AGENT_NAME }));
