import { useEffect, useRef } from "react";
import type { ChatItem } from "../types/chat";
import AssistantMessage from "./AssistantMessage";

interface Props {
  items: ChatItem[];
  pending: boolean;
}

export default function MessageList({ items, pending }: Props) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [items, pending]);

  return (
    <main className="messages" aria-live="polite">
      {items.length === 0 && !pending && (
        <p className="empty">Say hello — each reply shows its source, model, latency and token usage.</p>
      )}
      {items.map((item) =>
        item.role === "user" ? (
          <div key={item.id} className="bubble user" data-testid="user-message">
            {item.content}
          </div>
        ) : (
          <AssistantMessage key={item.id} content={item.content} metadata={item.metadata} />
        ),
      )}
      {pending && <div className="typing">Thinking…</div>}
      <div ref={endRef} />
    </main>
  );
}
