/**
 * Polls `predicate` until it returns true, or throws after `timeoutMs`.
 *
 * `AgentSession.run().wait()` and `session.waitForIdle()` only wait for the run's own speech
 * handle and the session's activity queue — neither one waits for a caller *outside* the run
 * (e.g. an orchestrator's `onEnter`) to finish reacting to an `AgentTask` completing. That
 * reaction is genuinely async but has no session-observable event of its own, so tests that
 * assert on it poll for the effect rather than sleeping a fixed guess.
 */
export async function waitUntil(
  predicate: () => boolean,
  options: { timeoutMs?: number; intervalMs?: number } = {},
): Promise<void> {
  const { timeoutMs = 2000, intervalMs = 10 } = options;
  const start = Date.now();
  while (!predicate()) {
    if (Date.now() - start > timeoutMs) {
      throw new Error(`waitUntil: condition not met within ${timeoutMs}ms`);
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}
