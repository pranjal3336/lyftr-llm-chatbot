import type { KeyboardEvent } from "react";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled: boolean;
}

export default function ChatComposer({ value, onChange, onSend, disabled }: Props) {
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (!disabled) onSend();
    }
  };
  return (
    <div className="composer">
      <textarea
        data-testid="chat-input"
        rows={2}
        placeholder="Type a message… (Enter to send, Shift+Enter for a new line)"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
      />
      <button type="button" data-testid="send-button" onClick={onSend} disabled={disabled}>
        Send
      </button>
    </div>
  );
}
