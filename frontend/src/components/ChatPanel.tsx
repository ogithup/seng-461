import { useEffect, useRef } from "react";
import type { ChatMessage } from "../hooks/useAgentSession";
import { ChatInput } from "./ChatInput";

interface Props {
  messages: ChatMessage[];
  sending: boolean;
  onSend: (text: string) => Promise<boolean>;
  blockedReason?: string;
}

export function ChatPanel({ messages, sending, onSend, blockedReason }: Props) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages.length, sending]);

  return (
    <section className="card chat-panel" aria-label="Chat">
      <h2>Chat</h2>
      <div className="messages" role="log" aria-live="polite">
        {messages.length === 0 && (
          <p className="muted empty">No messages yet. Tell the agent what to build.</p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`bubble ${m.role}`}>
            <span className="who">{m.role === "user" ? "You" : m.role === "agent" ? "Agent" : "Error"}</span>
            <p>{m.text}</p>
          </div>
        ))}
        {sending && (
          <div className="bubble agent pending">
            <span className="who">Agent</span>
            <p>Working on it…</p>
          </div>
        )}
        <div ref={endRef} />
      </div>
      <ChatInput
        onSend={onSend}
        disabled={sending || Boolean(blockedReason)}
        disabledReason={blockedReason}
      />
    </section>
  );
}
