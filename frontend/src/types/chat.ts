export type ResolutionSource = "LIVE_INFERENCE" | "LLM_CACHE";

export interface Metadata {
  resolution_source: ResolutionSource;
  model: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  key_id: string | null;
  fallback_attempts: number;
}

export interface ChatRequest {
  session_id: string;
  message: string;
  system_prompt?: string;
}

export interface ChatResponse {
  session_id: string;
  reply: string;
  metadata: Metadata;
}

export type ChatItem =
  | { id: number; role: "user"; content: string }
  | { id: number; role: "assistant"; content: string; metadata: Metadata };
