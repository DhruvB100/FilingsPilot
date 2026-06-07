"""
Chat sessions + history in Azure Cosmos DB (NoSQL).
One document per session, partition key /session_id.
If COSMOS_ENDPOINT isn't set (local dev) it just keeps everything in a dict.
"""
import os
import uuid
from datetime import datetime, timezone

from backend import config  # noqa: F401

MAX_MESSAGES = 40  # keep docs small, cosmos max is 2MB per item


def now():
    return datetime.now(timezone.utc).isoformat()


class Memory:
    def __init__(self):
        self.local = None
        if os.getenv("COSMOS_ENDPOINT"):
            from azure.cosmos import CosmosClient
            client = CosmosClient(os.getenv("COSMOS_ENDPOINT"), credential=os.getenv("COSMOS_KEY"))
            db = client.get_database_client(os.getenv("COSMOS_DATABASE", "filingspilot"))
            self.container = db.get_container_client("sessions")
        else:
            print("COSMOS_ENDPOINT not set, using in-memory sessions")
            self.local = {}

    def _read(self, session_id):
        if self.local is not None:
            return self.local.get(session_id)
        from azure.cosmos.exceptions import CosmosResourceNotFoundError
        try:
            return self.container.read_item(item=session_id, partition_key=session_id)
        except CosmosResourceNotFoundError:
            return None

    def _save(self, doc):
        if self.local is not None:
            self.local[doc["id"]] = doc
        else:
            self.container.upsert_item(doc)

    def get_session(self, session_id):
        return self._read(session_id)

    def new_session(self, first_question):
        sid = str(uuid.uuid4())
        doc = {"id": sid, "session_id": sid, "title": first_question[:80], "created_at": now(),
               "updated_at": now(), "messages": []}
        self._save(doc)
        return doc

    def add_turn(self, session_id, question, result):
        doc = self._read(session_id) or self.new_session(question)
        doc["messages"].append({"role": "user", "content": question, "ts": now()})
        doc["messages"].append({
            "role": "assistant", "content": result["answer"], "ts": now(),
            "sources": result.get("sources", {}), "steps": result.get("steps", []),
            "cost_usd": result.get("cost_usd"), "latency_s": result.get("latency_s"),
        })
        doc["messages"] = doc["messages"][-MAX_MESSAGES:]
        doc["updated_at"] = now()
        self._save(doc)

    def get_history(self, session_id, max_turns=3):
        """last few user/assistant messages, just the text, to give the agent some context"""
        doc = self._read(session_id) if session_id else None
        if not doc:
            return []
        return [{"role": m["role"], "content": m["content"]} for m in doc["messages"][-max_turns * 2:]]

    def list_sessions(self, limit=20):
        if self.local is not None:
            docs = sorted(self.local.values(), key=lambda d: d["updated_at"], reverse=True)
        else:
            docs = list(self.container.query_items(
                "SELECT c.id, c.title, c.updated_at FROM c ORDER BY c.updated_at DESC OFFSET 0 LIMIT @n",
                parameters=[{"name": "@n", "value": limit}], enable_cross_partition_query=True))
        return [{"id": d["id"], "title": d["title"], "updated_at": d["updated_at"]} for d in docs[:limit]]
