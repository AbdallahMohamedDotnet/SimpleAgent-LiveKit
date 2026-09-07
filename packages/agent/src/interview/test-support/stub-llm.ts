import {
  ChatContext,
  ChatMessage,
  DEFAULT_API_CONNECT_OPTIONS,
  FunctionCall,
  LLM,
  LLMStream,
  type ChatChunk,
  type ToolContextLike,
} from '@livekit/agents';

/**
 * A scripted `LLM` for driving `AgentSession.run()` in tests without any network call — the
 * framework's no-room test harness (dist/voice/agent_session.d.ts:524) still needs a real `LLM`
 * subclass to hand chunks back through, it just never has to be a real provider.
 *
 * Configured with an ordered script of "if the last user message matches this, emit this tool
 * call" entries. Each entry fires once; unmatched input falls through to a plain text reply so a
 * test never hangs waiting for a response that never comes.
 */
export interface ScriptedToolCall {
  match: RegExp;
  toolName: string;
  args: Record<string, unknown>;
}

export class StubLLM extends LLM {
  #script: ScriptedToolCall[];
  #fired = new Set<number>();

  constructor(script: ScriptedToolCall[]) {
    super();
    this.#script = script;
  }

  label(): string {
    return 'StubLLM';
  }

  override get provider(): string {
    return 'stub';
  }

  override get model(): string {
    return 'stub-1';
  }

  chat(options: { chatCtx: ChatContext; toolCtx?: ToolContextLike }): LLMStream {
    return new StubLLMStream(this, options, this.#script, this.#fired);
  }
}

class StubLLMStream extends LLMStream {
  #script: ScriptedToolCall[];
  #fired: Set<number>;

  constructor(
    llm: StubLLM,
    options: { chatCtx: ChatContext; toolCtx?: ToolContextLike },
    script: ScriptedToolCall[],
    fired: Set<number>,
  ) {
    super(llm, { ...options, connOptions: DEFAULT_API_CONNECT_OPTIONS });
    this.#script = script;
    this.#fired = fired;
  }

  protected async run(): Promise<void> {
    const lastUserText = this.chatCtx.items
      .filter((item): item is ChatMessage => item instanceof ChatMessage && item.role === 'user')
      .map((item) => item.textContent ?? '')
      .join(' ');

    for (let i = 0; i < this.#script.length; i++) {
      if (this.#fired.has(i)) continue;
      const entry = this.#script[i]!;
      if (entry.match.test(lastUserText ?? '')) {
        this.#fired.add(i);
        const chunk: ChatChunk = {
          id: `stub-${i}`,
          delta: {
            role: 'assistant',
            content: '',
            toolCalls: [
              new FunctionCall({
                callId: `call-${i}`,
                name: entry.toolName,
                args: JSON.stringify(entry.args),
              }),
            ],
          },
        };
        this.queue.put(chunk);
        return;
      }
    }

    // No script entry matched — reply with plain text so the test fails on an assertion, not a
    // hang.
    this.queue.put({
      id: 'stub-fallback',
      delta: { role: 'assistant', content: '(stub: no scripted match for this input)' },
    });
  }
}
