interface Props {
  value: string;
  onChange: (value: string) => void;
}

export default function SystemPromptBar({ value, onChange }: Props) {
  return (
    <div className="system-prompt">
      <label htmlFor="system-prompt-field">System prompt (optional)</label>
      <textarea
        id="system-prompt-field"
        data-testid="system-prompt-input"
        rows={2}
        placeholder="e.g. You are a pirate. Answer in one sentence."
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
