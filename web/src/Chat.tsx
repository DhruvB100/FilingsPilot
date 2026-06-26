import { useState, useRef, useEffect } from "react";
import { streamChat, citationLink, type Source, type Step, type FinalEvent } from "./api";

type Message = {
  role: "user" | "assistant";
  text: string;
  steps: Step[];
  final?: FinalEvent;
  streaming?: boolean;
  error?: string;
};

const EXAMPLES = [
  "How did Cenovus's revenue change from 2024 to 2025, and what reason did they give?",
  "Compare net income for RBC, TD and BMO in fiscal 2025",
  "What is Canadian Natural's 2026 production guidance?",
  "How fast did Shopify's revenue grow in 2025 and what drove it?",
];

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // update the last message (the assistant one being streamed)
  function updateLast(fn: (m: Message) => Message) {
    setMessages((prev) => [...prev.slice(0, -1), fn(prev[prev.length - 1])]);
  }

  async function ask(question: string) {
    if (!question.trim() || busy) return;
    setInput("");
    setBusy(true);
    setMessages((prev) => [
      ...prev,
      { role: "user", text: question, steps: [] },
      { role: "assistant", text: "", steps: [], streaming: true },
    ]);
    try {
      await streamChat(question, sessionId, (e) => {
        if (e.type === "session") setSessionId(e.session_id);
        else if (e.type === "token") updateLast((m) => ({ ...m, text: m.text + e.text }));
        else if (e.type === "plan" || e.type === "tool_call" || e.type === "tool_result")
          updateLast((m) => ({ ...m, steps: [...m.steps, e], text: e.type === "tool_result" ? "" : m.text }));
        else if (e.type === "final")
          // the final answer can differ from the streamed text (citation check / refusal)
          updateLast((m) => ({ ...m, text: e.answer, final: e, streaming: false }));
        else if (e.type === "error") updateLast((m) => ({ ...m, error: e.message, streaming: false }));
      });
    } catch (err) {
      updateLast((m) => ({ ...m, error: String(err), streaming: false }));
    }
    setBusy(false);
  }

  return (
    <div className="max-w-3xl mx-auto p-4 flex flex-col h-[calc(100vh-60px)]">
      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        {messages.length === 0 && (
          <div className="mt-10 text-center">
            <p className="text-slate-500 mb-4">Try one of these:</p>
            <div className="grid gap-2">
              {EXAMPLES.map((ex) => (
                <button key={ex} onClick={() => ask(ex)} className="text-left bg-white border rounded p-3 hover:bg-slate-100 text-sm">
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (m.role === "user" ? <UserBubble key={i} text={m.text} /> : <AssistantBubble key={i} m={m} />))}
        <div ref={bottomRef} />
      </div>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          ask(input);
        }}
      >
        <input
          className="flex-1 border rounded px-3 py-2"
          placeholder="Ask about revenue, capex, CET1 ratios, guidance..."
          value={input}
          maxLength={1000}
          onChange={(e) => setInput(e.target.value)}
        />
        <button className="bg-slate-800 text-white px-4 rounded disabled:opacity-50" disabled={busy}>
          {busy ? "..." : "Ask"}
        </button>
        <button
          type="button"
          className="border px-3 rounded text-sm"
          onClick={() => {
            setMessages([]);
            setSessionId(null);
          }}
        >
          New chat
        </button>
      </form>
    </div>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="bg-slate-800 text-white rounded-lg px-4 py-2 max-w-[80%]">{text}</div>
    </div>
  );
}

function AssistantBubble({ m }: { m: Message }) {
  const [showSteps, setShowSteps] = useState(false);
  const sources = m.final?.sources || {};

  return (
    <div className="bg-white border rounded-lg p-4">
      {m.error && <p className="text-red-600">{m.error}</p>}
      {m.streaming && !m.text && <p className="text-slate-400 text-sm">{lastStepLabel(m.steps)}</p>}
      <div className="whitespace-pre-wrap leading-relaxed">{renderAnswer(m.text.replace(/\*\*/g, ""), sources)}</div>

      {Object.keys(sources).length > 0 && (
        <div className="mt-3 border-t pt-2 text-sm space-y-1">
          {Object.entries(sources).map(([label, s]) => (
            <SourceLine key={label} label={label} s={s} />
          ))}
        </div>
      )}

      {m.steps.length > 0 && (
        <div className="mt-3 text-sm">
          <button className="text-slate-500 underline" onClick={() => setShowSteps(!showSteps)}>
            {showSteps ? "Hide" : "Show"} reasoning steps ({m.steps.length})
          </button>
          {showSteps && <StepsPanel steps={m.steps} />}
        </div>
      )}
      {m.final && (
        <p className="text-xs text-slate-400 mt-2">
          {m.final.latency_s}s · ${m.final.cost_usd.toFixed(4)}
        </p>
      )}
    </div>
  );
}

function lastStepLabel(steps: Step[]) {
  const last = steps[steps.length - 1];
  if (!last) return "Planning...";
  if (last.type === "plan") return "Planning done, looking things up...";
  if (last.type === "tool_call") return `Running ${last.tool}...`;
  return "Reading results...";
}

// turns "[S1]" / "[F1, S2]" in the answer into clickable citation chips
function renderAnswer(text: string, sources: Record<string, Source>) {
  const parts = text.split(/(\[[SF]\d+(?:,\s*[SF]\d+)*\])/g);
  return parts.map((part, i) => {
    if (!/^\[[SF]\d+/.test(part)) return <span key={i}>{part}</span>;
    const labels = part.slice(1, -1).split(/,\s*/);
    return (
      <span key={i}>
        {labels.map((label) => {
          const s = sources[label];
          const link = s ? citationLink(s) : undefined;
          return link ? (
            <a key={label} href={link} target="_blank" rel="noreferrer" className="text-xs bg-blue-100 text-blue-800 rounded px-1 mx-0.5 hover:bg-blue-200">
              {label}
            </a>
          ) : (
            <span key={label} title={s?.sql} className="text-xs bg-emerald-100 text-emerald-800 rounded px-1 mx-0.5 cursor-help">
              {label}
            </span>
          );
        })}
      </span>
    );
  });
}

function SourceLine({ label, s }: { label: string; s: Source }) {
  if (s.type === "financials") {
    return (
      <div className="text-slate-600">
        <span className="font-mono text-emerald-700">[{label}]</span> SEC XBRL financial data
        <code className="block text-xs bg-slate-50 p-1 mt-0.5 overflow-x-auto">{s.sql}</code>
      </div>
    );
  }
  return (
    <div className="text-slate-600">
      <span className="font-mono text-blue-700">[{label}]</span>{" "}
      <a href={citationLink(s)} target="_blank" rel="noreferrer" className="underline">
        {s.company} {s.fiscal_year} {s.doc_type}, page {s.page}
      </a>{" "}
      <span className="text-slate-400">· {s.section}</span>
    </div>
  );
}

function StepsPanel({ steps }: { steps: Step[] }) {
  return (
    <ol className="mt-2 space-y-2 border-l-2 pl-3">
      {steps.map((s, i) => (
        <li key={i}>
          {s.type === "plan" && (
            <div>
              <b>Plan</b>
              <ul className="list-disc ml-5">
                {s.steps.map((p, j) => (
                  <li key={j}>{p}</li>
                ))}
              </ul>
            </div>
          )}
          {s.type === "tool_call" && (
            <div>
              <b>Call {s.tool}</b>
              <code className="block text-xs bg-slate-50 p-1 overflow-x-auto">{JSON.stringify(s.args)}</code>
            </div>
          )}
          {s.type === "tool_result" && (
            <div className="text-slate-500">
              <b>Result from {s.tool}</b>
              <pre className="text-xs bg-slate-50 p-1 whitespace-pre-wrap max-h-32 overflow-y-auto">{s.preview}</pre>
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}
