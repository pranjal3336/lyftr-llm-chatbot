import type { Metadata } from "../types/chat";

interface Props {
  content: string;
  metadata: Metadata;
}

/** Each meta-* element holds ONLY its raw value; labels live in sibling spans. */
export default function AssistantMessage({ content, metadata: m }: Props) {
  return (
    <article className="bubble assistant" data-testid="assistant-message">
      <p className="reply">{content}</p>
      <div className="meta">
        <span className="meta-item">
          <span className="meta-label">Source</span>
          <span data-testid="meta-source" className={`badge ${m.resolution_source}`}>{m.resolution_source}</span>
        </span>
        <span className="meta-item">
          <span className="meta-label">Model</span>
          <span data-testid="meta-model">{m.model}</span>
        </span>
        <span className="meta-item">
          <span className="meta-label">Latency</span>
          <span data-testid="meta-latency">{`${m.latency_ms} ms`}</span>
        </span>
        <span className="meta-item">
          <span className="meta-label">In:</span>
          <span data-testid="meta-input-tokens">{m.input_tokens}</span>
        </span>
        <span className="meta-item">
          <span className="meta-label">Out:</span>
          <span data-testid="meta-output-tokens">{m.output_tokens}</span>
        </span>
        <span className="meta-item subtle">
          <span className="meta-label">Key</span>
          <span data-testid="meta-key-id">{m.key_id ?? "—"}</span>
        </span>
        <span className="meta-item subtle">
          <span className="meta-label">Fallbacks</span>
          <span data-testid="meta-fallback-attempts">{m.fallback_attempts}</span>
        </span>
      </div>
    </article>
  );
}
