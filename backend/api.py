"""
FastAPI app. Run: uvicorn backend.api:app --reload
"""
import os
import json
import glob
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend import telemetry

# has to run before the FastAPI app is created so requests get auto traced
telemetry.setup()

from backend.agent import stream_agent, run_agent  # noqa: E402
from backend.memory import Memory  # noqa: E402
from backend.tools import make_tools  # noqa: E402

app = FastAPI(title="FilingsPilot")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
memory = Memory()

MAX_QUESTION_CHARS = 1000


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=MAX_QUESTION_CHARS)
    session_id: str | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


def sse(event):
    return f"data: {json.dumps(event, default=str)}\n\n"


@app.post("/chat")
def chat(req: ChatRequest):
    """streams Server-Sent Events: session, plan, tool_call, tool_result, token, final (or error)"""
    session = memory.get_session(req.session_id) if req.session_id else None
    if not session:
        session = memory.new_session(req.question)
    history = memory.get_history(session["id"])

    def events():
        yield sse({"type": "session", "session_id": session["id"]})
        try:
            for event in stream_agent(req.question, history):
                if event["type"] == "final":
                    event.pop("all_sources", None)
                    event.pop("context", None)
                    memory.add_turn(session["id"], req.question, event)
                yield sse(event)
        except Exception as e:
            print("chat error:", repr(e))
            yield sse({"type": "error", "message": "Something went wrong answering that question."})

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/chat/sync")
def chat_sync(req: ChatRequest):
    history = memory.get_history(req.session_id) if req.session_id else []
    result = run_agent(req.question, history)
    result.pop("all_sources", None)
    result.pop("context", None)
    return result


@app.get("/sessions")
def sessions():
    return memory.list_sessions()


@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    doc = memory.get_session(session_id)
    if not doc:
        raise HTTPException(404, "session not found")
    return doc


@app.get("/evals")
def evals():
    """summary of every eval run, for the eval results page"""
    runs = []
    for path in sorted(glob.glob("evals/results/*.json")):
        with open(path) as f:
            data = json.load(f)
        runs.append({"file": os.path.basename(path), **data.get("summary", {})})
    return runs


# --- the same tools as plain endpoints, the MCP server calls these ---

class SearchRequest(BaseModel):
    query: str
    tickers: list[str] | None = None
    years: list[int] | None = None


class SQLRequest(BaseModel):
    sql: str


class CalcRequest(BaseModel):
    operation: str
    a: float
    b: float | None = None
    years: float | None = None


class FlagRequest(BaseModel):
    summary: str
    details: str
    ticker: str


def tool(name):
    tools = {t.name: t for t in make_tools({})}
    return tools[name]


@app.post("/tools/search_filings")
def tool_search(req: SearchRequest):
    return {"result": tool("search_filings").invoke(req.model_dump())}


@app.post("/tools/query_financials")
def tool_sql(req: SQLRequest):
    return {"result": tool("query_financials").invoke(req.model_dump())}


@app.post("/tools/calculate")
def tool_calc(req: CalcRequest):
    return {"result": tool("calculate").invoke(req.model_dump())}


@app.post("/tools/flag_issue")
def tool_flag(req: FlagRequest):
    return {"result": tool("flag_issue").invoke(req.model_dump())}
