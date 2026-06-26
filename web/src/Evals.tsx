import { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid, ResponsiveContainer } from "recharts";
import { API_URL } from "./api";

type Run = {
  file: string;
  commit: string;
  commit_date: string;
  provider: string;
  subset: string;
  questions: number;
  answer_correctness: number;
  faithfulness: number;
  citation_accuracy: number;
  recall_at_5: number;
  tool_accuracy: number;
  p95_latency_s: number;
  cost_per_question_usd: number;
};

const METRICS = [
  { key: "answer_correctness", color: "#1e293b" },
  { key: "faithfulness", color: "#2563eb" },
  { key: "citation_accuracy", color: "#16a34a" },
  { key: "recall_at_5", color: "#d97706" },
  { key: "tool_accuracy", color: "#9333ea" },
];

export default function Evals() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API_URL}/evals`)
      .then((r) => r.json())
      .then((data: Run[]) => setRuns(data.sort((a, b) => a.commit_date.localeCompare(b.commit_date))))
      .catch((e) => setError(String(e)));
  }, []);

  // chart = full azure runs over time
  const chartData = runs
    .filter((r) => r.provider === "azure" && r.subset === "full")
    .map((r) => ({ ...r, label: `${r.commit_date.slice(0, 10)} (${r.commit})` }));

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-8">
      <section>
        <h2 className="font-bold text-lg mb-1">Scores over time</h2>
        <p className="text-sm text-slate-500 mb-4">Full 50-question golden set, Azure OpenAI (gpt-5-mini), one point per commit.</p>
        {error && <p className="text-red-600">{error}</p>}
        <div className="bg-white border rounded p-4 h-80">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="label" fontSize={11} />
              <YAxis domain={[0, 1]} />
              <Tooltip />
              <Legend />
              {METRICS.map((m) => (
                <Line key={m.key} type="monotone" dataKey={m.key} stroke={m.color} dot />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section>
        <h2 className="font-bold text-lg mb-2">All runs</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm bg-white border">
            <thead className="bg-slate-100">
              <tr>
                {["commit", "provider", "subset", "n", "correct", "faithful", "citations", "recall@5", "tools", "p95 s", "$/question"].map((h) => (
                  <th key={h} className="text-left p-2">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.file} className="border-t">
                  <td className="p-2 font-mono">{r.commit} <span className="text-slate-400">{r.commit_date.slice(0, 10)}</span></td>
                  <td className="p-2">{r.provider}</td>
                  <td className="p-2">{r.subset}</td>
                  <td className="p-2">{r.questions}</td>
                  <td className="p-2">{pct(r.answer_correctness)}</td>
                  <td className="p-2">{pct(r.faithfulness)}</td>
                  <td className="p-2">{pct(r.citation_accuracy)}</td>
                  <td className="p-2">{pct(r.recall_at_5)}</td>
                  <td className="p-2">{pct(r.tool_accuracy)}</td>
                  <td className="p-2">{r.p95_latency_s}</td>
                  <td className="p-2">{r.cost_per_question_usd?.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function pct(v: number | null) {
  return v == null ? "-" : `${Math.round(v * 100)}%`;
}
