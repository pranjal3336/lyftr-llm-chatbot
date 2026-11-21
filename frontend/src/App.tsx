import { useCallback, useRef, useState } from "react";
import { ApiError, sendChat } from "./api/client";
import ChatComposer from "./components/ChatComposer";
import ErrorBanner from "./components/ErrorBanner";
import Header from "./components/Header";
import MessageList from "./components/MessageList";
import SystemPromptBar from "./components/SystemPromptBar";
import type { ChatItem } from "./types/chat";

function newSessionId(): string {
  const raw =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : Math.random().toString(16).slice(2) + Date.now().toString(16);
  return `s-${raw.replace(/-/g, "").slice(0, 8)}`;
}

export default function App() {
  // A fresh session on every page load (never restored from storage).
  const [sessionId, setSessionId] = useState<string>(newSessionId);
  const [items, setItems] = useState<ChatItem[]>([]);
  const [draft, setDraft] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [simulation, setSimulation] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nextId = useRef(1);
  const generation = useRef(0); // invalidates in-flight replies after "New Session"

  const send = useCallback(async () => {
    const message = draft.trim();
    if (!message || pending) return;

    const userId = nextId.current++;
    const gen = generation.current;
    setItems((prev) => [...prev, { id: userId, role: "user", content: message }]);
    setDraft(""); // reset immediately
    setError(null);
    setPending(true);

    try {
      const res = await sendChat(
        { session_id: sessionId, message, ...(systemPrompt.trim() ? { system_prompt: systemPrompt } : {}) },
        simulation || null,
      );
      if (gen !== generation.current) return;
      setItems((prev) => [
        ...prev,
        { id: nextId.current++, role: "assistant", content: res.reply, metadata: res.metadata },
      ]);
    } catch (e) {
      if (gen !== generation.current) return;
      // The backend did not persist this turn, so roll back the optimistic user bubble.
      setItems((prev) => prev.filter((it) => it.id !== userId));
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      if (gen === generation.current) setPending(false);
    }
  }, [draft, pending, sessionId, systemPrompt, simulation]);

  const newSession = () => {
    generation.current += 1;
    setSessionId(newSessionId());
    setItems([]);
    setDraft("");
    setError(null);
    setPending(false);
  };

  return (
    <div className="app">
      <Header
        sessionId={sessionId}
        simulation={simulation}
        onSimulationChange={setSimulation}
        onNewSession={newSession}
      />
      <SystemPromptBar value={systemPrompt} onChange={setSystemPrompt} />
      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      <MessageList items={items} pending={pending} />
      <ChatComposer value={draft} onChange={setDraft} onSend={send} disabled={pending} />
    </div>
  );
}
