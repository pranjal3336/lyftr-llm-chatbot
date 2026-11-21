import type { ChatRequest, ChatResponse } from "../types/chat";

const RAW_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
export const API_BASE_URL = RAW_BASE.replace(/\/+$/, "");

export class ApiError extends Error {}

/** Turn FastAPI's `detail` (string or list of validation errors) into one readable sentence. */
function describeDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((d) => {
      if (d && typeof d === "object" && "msg" in d) {
        const loc = Array.isArray((d as { loc?: unknown[] }).loc)
          ? ((d as { loc: unknown[] }).loc.filter((x) => x !== "body").join(".") || "request")
          : "request";
        return `${loc}: ${String((d as { msg: unknown }).msg).replace(/^Value error, /, "")}`;
      }
      return String(d);
    });
    return parts.join("; ");
  }
  return "Unexpected error response from the server.";
}

export async function sendChat(
  body: ChatRequest,
  simulateFailure: string | null,
): Promise<ChatResponse> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (simulateFailure) headers["X-Simulate-Failure"] = simulateFailure;

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/chat`, { method: "POST", headers, body: JSON.stringify(body) });
  } catch {
    throw new ApiError("Cannot reach the server. Check your connection and try again.");
  }

  let payload: unknown = null;
  try {
    payload = await res.json();
  } catch {
    /* non-JSON body */
  }

  if (!res.ok) {
    const detail = payload && typeof payload === "object" && "detail" in payload
      ? (payload as { detail: unknown }).detail
      : undefined;
    const text = describeDetail(detail);
    if (res.status === 422) throw new ApiError(`Invalid message — ${text}`);
    if (res.status === 503) throw new ApiError(`Service unavailable — ${text}`);
    throw new ApiError(`Request failed (${res.status}) — ${text}`);
  }
  return payload as ChatResponse;
}
