"""
Hybrid search = keyword (postgres full text) + vector (pgvector), merged with reciprocal rank fusion.
Run: python -m backend.search "cenovus capital spending 2025" CVE
"""
import sys

from backend.db import get_conn
from backend.embeddings import embed_one

RRF_K = 60  # standard value from the RRF paper
CANDIDATES = 40

_conn = None


def conn():
    global _conn
    if _conn is None or _conn.closed:
        _conn = get_conn()
    return _conn


def build_filters(tickers, years):
    where, params = [], []
    if tickers:
        where.append("ticker = ANY(%s)")
        params.append([t.upper() for t in tickers])
    if years:
        where.append("fiscal_year = ANY(%s)")
        params.append([int(y) for y in years])
    return where, params


def vector_search(query, tickers=None, years=None, limit=CANDIDATES):
    where, params = build_filters(tickers, years)
    sql = "SELECT id FROM chunks"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY embedding <=> %s::vector LIMIT %s"
    rows = conn().execute(sql, params + [embed_one(query), limit]).fetchall()
    return [r[0] for r in rows]


def keyword_search(query, tickers=None, years=None, limit=CANDIDATES):
    where, params = build_filters(tickers, years)
    # websearch_to_tsquery ANDs all words which is too strict for questions,
    # so OR the words together and let ts_rank sort it out
    words = [w for w in query.replace("'", " ").split() if w.isalnum()]
    if not words:
        return []
    where.append("tsv @@ to_tsquery('english', %s)")
    tsquery = " | ".join(words)
    sql = f"""SELECT id FROM chunks WHERE {' AND '.join(where)}
              ORDER BY ts_rank_cd(tsv, to_tsquery('english', %s)) DESC LIMIT %s"""
    rows = conn().execute(sql, params + [tsquery, tsquery, limit]).fetchall()
    return [r[0] for r in rows]


def hybrid_search(query, tickers=None, years=None, k=5):
    vec_ids = vector_search(query, tickers, years)
    kw_ids = keyword_search(query, tickers, years)

    scores = {}
    for rank, cid in enumerate(vec_ids):
        scores[cid] = scores.get(cid, 0) + 1 / (RRF_K + rank + 1)
    for rank, cid in enumerate(kw_ids):
        scores[cid] = scores.get(cid, 0) + 1 / (RRF_K + rank + 1)
    top = sorted(scores, key=scores.get, reverse=True)[:k]
    if not top:
        return []

    rows = conn().execute(
        """SELECT id, ticker, company, fiscal_year, form, doc_type, doc_file, doc_url, page, section, content
           FROM chunks WHERE id = ANY(%s)""",
        (top,),
    ).fetchall()
    cols = ["id", "ticker", "company", "fiscal_year", "form", "doc_type", "doc_file", "doc_url", "page", "section", "content"]
    by_id = {r[0]: dict(zip(cols, r)) for r in rows}
    results = []
    for cid in top:
        r = by_id[cid]
        r["score"] = round(scores[cid], 4)
        results.append(r)
    return results


if __name__ == "__main__":
    q = sys.argv[1]
    tickers = sys.argv[2].split(",") if len(sys.argv) > 2 else None
    for r in hybrid_search(q, tickers):
        print(f"[{r['score']}] {r['ticker']} {r['fiscal_year']} {r['doc_type']} p.{r['page']} | {r['section']}")
        print("   ", r["content"][:250].replace("\n", " "))
