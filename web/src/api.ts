export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export type Source = {
  type: "filing" | "financials" | "jira";
  company?: string;
  ticker?: string;
  fiscal_year?: number;
  doc_type?: string;
  page?: number;
  section?: string;
  url?: string;
  snippet?: string;
  sql?: string;
  key?: string;
};

export type Step =
  | { type: "plan"; steps: string[] }
  | { type: "tool_call"; tool: string; args: Record<string, unknown> }
  | { type: "tool_result"; tool: string; preview: string };

export type FinalEvent = {
  type: "final";
  answer: string;
  sources: Record<string, Source>;
  steps: Step[];
  cost_usd: number;
  latency_s: number;
};

// POST /chat returns server sent events, EventSource only does GET so read the stream by hand
export async function streamChat(
  question: string,
  sessionId: string | null,
  onEvent: (e: any) => void
) {
  const res = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: sessionId }),
  });
  if (!res.ok || !res.body) {
    throw new Error(`API error ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // events are separated by a blank line, the last piece might be half an event
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      if (part.startsWith("data: ")) {
        onEvent(JSON.parse(part.slice(6)));
      }
    }
  }
}

// link that opens the filing and scrolls to the cited text (chrome/edge text fragments)
export function citationLink(s: Source) {
  if (!s.url) return undefined;
  const line = (s.snippet || "").split("\n").find((l) => l.length > 50 && !l.includes("|"));
  if (!line) return s.url;
  const words = line.split(/\s+/).slice(0, 8).join(" ");
  return `${s.url}#:~:text=${encodeURIComponent(words)}`;
}
