import { useState } from "react";
import Chat from "./Chat";
import Evals from "./Evals";

export default function App() {
  const [page, setPage] = useState<"chat" | "evals">("chat");

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b px-6 py-3 flex items-center gap-6">
        <h1 className="font-bold text-lg">FilingsPilot</h1>
        <span className="text-sm text-slate-500">Ask about 10 Canadian companies' SEC annual filings</span>
        <nav className="ml-auto flex gap-2">
          <button
            className={`px-3 py-1 rounded ${page === "chat" ? "bg-slate-800 text-white" : "hover:bg-slate-100"}`}
            onClick={() => setPage("chat")}
          >
            Chat
          </button>
          <button
            className={`px-3 py-1 rounded ${page === "evals" ? "bg-slate-800 text-white" : "hover:bg-slate-100"}`}
            onClick={() => setPage("evals")}
          >
            Eval results
          </button>
        </nav>
      </header>
      <main className="flex-1">{page === "chat" ? <Chat /> : <Evals />}</main>
    </div>
  );
}
